import dataclasses
import functools
import itertools
import json
from abc import abstractmethod
from typing import Any, Callable, List, Protocol

from flask_principal import Identity


@dataclasses.dataclass
class LateAction:
    method_name: str
    entry: StreamEntry
    params: dict[str, Any]


class OAIRuleTransformer(BaseTransformer):
    def __init__(self, identity: Identity, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.late_actions: list[LateAction] = []
        self.identity = identity

    def apply(self, batch: StreamBatch, *args: Any, **kwargs: Any) -> StreamBatch:
        if not len(batch.entries):
            return batch
        for entry in batch.entries:
            entry.transformed = {}  # type: ignore # extending the instance temporarily
            entry.processed = set()  # type: ignore # extending the instance temporarily
            try:
                self.transform(entry)
            except Exception as e:
                entry.errors.append(StreamEntryError.from_exception(e))
        try:
            self.finish_transformation(batch.entries)
        except Exception as e:
            batch.errors.append(StreamEntryError.from_exception(e))
        return batch

    @abstractmethod
    def transform(self, entry: StreamEntry) -> None:
        """Please add your code here"""
        raise NotImplementedError("Please implement the transform method")

    def register_late_action(
        self, method_name: str, entry: StreamEntry, **action_params: Any
    ):
        self.late_actions.append(LateAction(method_name, entry, action_params))

    def finish_transformation(self, entries: List[StreamEntry]):
        for action in self.late_actions:
            getattr(self, action.method_name)(action.entry, **action.params)

        for entry in entries:
            entry.entry = entry.transformed  # type: ignore # extending the instance temporarily
            delattr(entry, "transformed")
            delattr(entry, "processed")


class RuleMethod[T](Protocol):
    def __call__(self, md: dict[str, Any], entry: StreamEntry, value: T) -> None: ...


class RuleWrapperMethod[T](Protocol):
    def __call__(self, md: dict[str, Any], entry: StreamEntry) -> None: ...


def matches[T](
    *args: Any, first_only: bool = False, paired: bool = False, unique: bool = False
) -> Callable[[RuleMethod[T]], RuleWrapperMethod[T]]:

    def wrapper(f: RuleMethod[T]) -> RuleWrapperMethod[T]:

        @functools.wraps(f)
        def wrapped(md: dict[str, Any], entry: StreamEntry):
            entry.processed.update(args)  # type: ignore # extending the instance temporarily
            untransformed_data = entry.entry
            if paired:
                vals: list[list[Any] | tuple[Any, ...]] = []
                for arg in args:
                    val = untransformed_data.get(arg)
                    if val is None:
                        val = []
                    elif not isinstance(val, (list, tuple)):
                        val = [val]
                    vals.append(val)

                if all(len(x) == 0 for x in vals):
                    return

                # zip longest
                items: set[Any] = set()
                for v in itertools.zip_longest(*vals):
                    if not unique or tuple(v) not in items:
                        f(md, entry, v)
                        items.add(tuple(v))
                return

            items: set[Any] = set()
            for arg in args:
                if arg in untransformed_data:
                    val = untransformed_data[arg]
                    if isinstance(val, (list, tuple)):
                        for vv in val:
                            if vv is None or vv == "":
                                continue

                            if not unique or vv not in items:
                                f(md, entry, vv)
                                items.add(vv)
                    else:
                        if val is None or val == "":
                            continue

                        if not unique or val not in items:
                            f(md, entry, val)
                            items.add(val)
                    if first_only:
                        break

        return wrapped

    return wrapper


def matches_grouped[T](
    *args: Any, group: List[str], unique: bool = False
) -> Callable[[RuleMethod[T]], RuleWrapperMethod[T]]:
    def wrapper(f: RuleMethod[T]) -> RuleWrapperMethod[T]:
        @functools.wraps(f)
        def wrapped(md: dict[str, Any], entry: StreamEntry):
            entry.processed.update(args)  # type: ignore
            untransformed_data = entry.entry

            expected_length = None
            for arg in args:
                if arg not in group:
                    val = untransformed_data.get(arg)
                    if isinstance(val, (list, tuple)):
                        expected_length = len(val)
                        break
                    elif val is not None:
                        expected_length = 1
                        break

            vals: list[list[Any] | tuple[Any, ...]] = []
            for arg in args:
                val = untransformed_data.get(arg)
                if val is None:
                    val = []
                elif arg in group and isinstance(val, tuple):
                    if expected_length is not None and len(val) != expected_length:
                        # single record with multiple values - keep together
                        val = [val]
                    else:
                        # multiple records - treat normally
                        val = list(val)
                elif isinstance(val, (list, tuple)):
                    val = list(val)
                else:
                    val = [val]
                vals.append(val)

            if all(len(x) == 0 for x in vals):
                return

            # zip longest
            items: set[Any] = set()
            for v in itertools.zip_longest(*vals):
                if not unique or tuple(v) not in items:
                    f(md, entry, v)
                    items.add(tuple(v))

        return wrapped

    return wrapper


def deduplicate(md: dict[str, Any], what: str):
    contribs = [json.dumps(x, sort_keys=True) for x in md.get(what, [])]
    for idx in range(len(contribs) - 1, -1, -1):
        for pidx in range(0, idx):
            if contribs[idx] == contribs[pidx]:
                del contribs[idx]
                del md[what][idx]
                break


def ignore(entry: StreamEntry, *args: str):
    entry.processed.update(args)  # type: ignore # extending the instance temporarily


def make_array(*vals_and_conditions: Any) -> list[Any]:
    """
    make array from list of [condition, value, condition, value, ...]
    If condition is true, add value to the resulting list, otherwise silently drop
    condition and value might be callables
    """
    ret: list[Any] = []
    for i in range(0, len(vals_and_conditions), 2):
        cond = vals_and_conditions[i]
        if callable(cond):
            cond = cond()
        if not cond:
            continue
        val = vals_and_conditions[i + 1]
        if callable(val):
            val = val()
        ret.append(val)
    return ret


def make_dict(*pairs: Any) -> dict[str, Any]:
    ret: dict[str, Any] = {}
    for i in range(0, len(pairs), 2):
        k = pairs[i]
        v = pairs[i + 1]
        if v:
            ret[k] = v
    return ret
