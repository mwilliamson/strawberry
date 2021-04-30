from __future__ import annotations

import enum
import inspect
import typing
from typing import Any, Dict, List, Optional, Type, Iterable

from typing_extensions import Annotated, get_args, get_origin

from strawberry.annotation import StrawberryAnnotation
from strawberry.type import StrawberryType, StrawberryList, StrawberryOptional

from .exceptions import MultipleStrawberryArgumentsError, UnsupportedTypeError
from .scalars import is_scalar
from .types.types import undefined
from .utils.str_converters import to_camel_case


class StrawberryArgumentAnnotation:
    description: Optional[str]

    def __init__(self, description: Optional[str] = None):
        self.description = description


class StrawberryArgument:
    def __init__(
        self,
        # TODO: this optional will probably go away when we have StrawberryList
        python_name: Optional[str],
        graphql_name: Optional[str],
        type_annotation: StrawberryAnnotation,
        origin: Optional[Type] = None,
        is_subscription: bool = False,
        description: Optional[str] = None,
        default_value: Any = undefined,
    ) -> None:
        self.python_name = python_name
        self._graphql_name = graphql_name
        self.origin = origin
        self.is_subscription = is_subscription
        self.description = description
        self._type: Optional[StrawberryType] = None
        self.type_annotation = type_annotation

        # TODO: Consider moving this logic to a function
        default_value = (
            undefined
            if default_value is inspect.Parameter.empty or is_unset(default_value)
            else default_value
        )
        self.default_value = default_value

        if self._annotation_is_annotated(type_annotation):
            self._parse_annotated()

    @property
    def graphql_name(self) -> Optional[str]:
        if self._graphql_name:
            return self._graphql_name
        if self.python_name:
            return to_camel_case(self.python_name)
        return None

    @property
    def type(self) -> StrawberryType:
        return self.type_annotation.resolve()

    @classmethod
    def _annotation_is_annotated(cls, annotation: StrawberryAnnotation) -> bool:
        return get_origin(annotation.annotation) is Annotated

    def _parse_annotated(self):
        annotated_args = get_args(self.type_annotation.annotation)

        # The first argument to Annotated is always the underlying type
        self.type_annotation = StrawberryAnnotation(annotated_args[0])

        # Find any instances of StrawberryArgumentAnnotation
        # in the other Annotated args, raising an exception if there
        # are multiple StrawberryArgumentAnnotations
        argument_annotation_seen = False
        for arg in annotated_args[1:]:
            if isinstance(arg, StrawberryArgumentAnnotation):
                if argument_annotation_seen:
                    raise MultipleStrawberryArgumentsError(
                        field_name=self.origin.__name__,
                        argument_name=self.python_name,
                    )

                argument_annotation_seen = True

                self.description = arg.description
                # TODO: This is where we'd pull the name out of the Annotated


class _Unset:
    def __str__(self):
        return ""

    def __bool__(self):
        return False


UNSET: Any = _Unset()


def is_unset(value: Any) -> bool:
    return type(value) is _Unset


def convert_argument(value: object, type_: StrawberryType) -> object:
    if value is None:
        return None

    if is_unset(value):
        return value

    if isinstance(type_, StrawberryOptional):
        return convert_argument(value, type_.of_type)

    if isinstance(type_, StrawberryList):
        value_list = typing.cast(Iterable, value)
        return [convert_argument(x, type_.of_type) for x in value_list]

    if is_scalar(type_):
        return value

    # Convert Enum fields to instances using the value. This is safe
    # because graphql-core has already validated the input.
    if isinstance(type_, enum.EnumMeta):
        return type_(value)  # type: ignore

    if hasattr(type_, "_type_definition"):  # TODO: Replace with StrawberryInputObject
        assert type_._type_definition.is_input

        kwargs = {}

        for field in type_._type_definition.fields:
            # TODO: cast value as a protocol that supports __getitem__
            if field.graphql_name in value:
                kwargs[field.python_name] = convert_argument(
                    value[field.graphql_name], field.type
                )

        return type_(**kwargs)

    raise UnsupportedTypeError(type_)


def convert_arguments(
    value: Dict[str, Any],
    arguments: List[StrawberryArgument],
) -> Dict[str, Any]:
    """Converts a nested dictionary to a dictionary of actual types.

    It deals with conversion of input types to proper dataclasses and
    also uses a sentinel value for unset values."""

    if not arguments:
        return {}

    kwargs = {}

    for argument in arguments:
        if argument.graphql_name in value:
            current_value = value[argument.graphql_name]
            kwargs[argument.python_name] = convert_argument(
                value=current_value,
                type_=argument.type,
            )

    return kwargs


def argument(description: Optional[str] = None) -> StrawberryArgumentAnnotation:
    return StrawberryArgumentAnnotation(description=description)


# TODO: check exports
__all__ = [
    "StrawberryArgument",
    "StrawberryArgumentAnnotation",
    "UNSET",
    "argument",
    "get_arguments_from_annotations",
    "is_unset",
    "undefined",
]
