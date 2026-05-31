"""Tests for app/serializers/ Phase G modules."""

from __future__ import annotations

import base64
import json

import pytest

# ---------------------------------------------------------------------------
# contracts
# ---------------------------------------------------------------------------
from app.serializers.contracts import FieldDescriptor, FieldType, SerializerContract


class TestFieldDescriptor:
    def test_default_serialized_name_equals_field_name(self):
        fd = FieldDescriptor(name="title", field_type=FieldType.STRING)
        assert fd.serialized_name == "title"

    def test_alias_overrides_serialized_name(self):
        fd = FieldDescriptor(name="judge_id", field_type=FieldType.INTEGER, alias="id")
        assert fd.serialized_name == "id"

    def test_required_true_by_default(self):
        fd = FieldDescriptor(name="x", field_type=FieldType.STRING)
        assert fd.required is True
        assert not fd.is_optional()

    def test_optional_field(self):
        fd = FieldDescriptor(name="x", field_type=FieldType.STRING, required=False)
        assert fd.is_optional()

    def test_default_default_is_none(self):
        fd = FieldDescriptor(name="x", field_type=FieldType.STRING)
        assert fd.default is None

    def test_custom_default(self):
        fd = FieldDescriptor(
            name="score", field_type=FieldType.FLOAT, required=False, default=0.0
        )
        assert fd.default == 0.0

    def test_field_type_enum_values(self):
        assert FieldType.STRING == "string"
        assert FieldType.INTEGER == "integer"
        assert FieldType.ANY == "any"


class TestSerializerContract:
    def _make(self) -> SerializerContract:
        c = SerializerContract(name="Test")
        c.add_field(FieldDescriptor("name", FieldType.STRING))
        c.add_field(
            FieldDescriptor("age", FieldType.INTEGER, required=False, default=0)
        )
        return c

    def test_add_field(self):
        c = self._make()
        assert c.has_field("name")
        assert c.has_field("age")

    def test_add_duplicate_raises(self):
        c = self._make()
        with pytest.raises(ValueError):
            c.add_field(FieldDescriptor("name", FieldType.STRING))

    def test_remove_field(self):
        c = self._make()
        removed = c.remove_field("age")
        assert removed is True
        assert not c.has_field("age")

    def test_remove_nonexistent_returns_false(self):
        c = self._make()
        assert c.remove_field("nope") is False

    def test_get_field(self):
        c = self._make()
        fd = c.get_field("name")
        assert fd is not None
        assert fd.field_type == FieldType.STRING

    def test_get_field_missing_returns_none(self):
        c = self._make()
        assert c.get_field("zzz") is None

    def test_required_fields_list(self):
        c = self._make()
        names = [fd.name for fd in c.required_fields()]
        assert names == ["name"]

    def test_optional_fields_list(self):
        c = self._make()
        names = [fd.name for fd in c.optional_fields()]
        assert names == ["age"]

    def test_field_names(self):
        c = self._make()
        assert set(c.field_names()) == {"name", "age"}

    def test_validate_keys_missing(self):
        c = self._make()
        missing, extra = c.validate_keys({"age": 5})
        assert "name" in missing
        assert extra == []

    def test_validate_keys_extra_non_strict(self):
        c = self._make()
        c.strict = False
        missing, extra = c.validate_keys({"name": "Alice", "unknown": 1})
        assert missing == []
        assert "unknown" in extra

    def test_is_valid_true(self):
        c = self._make()
        assert c.is_valid({"name": "Alice"})

    def test_is_valid_false_when_missing_required(self):
        c = self._make()
        assert not c.is_valid({})

    def test_is_valid_strict_rejects_extra(self):
        c = self._make()
        c.strict = True
        assert not c.is_valid({"name": "Alice", "extra": True})

    def test_serialize_applies_default(self):
        c = self._make()
        result = c.serialize({"name": "Bob"})
        assert result["age"] == 0

    def test_serialize_applies_alias(self):
        c = SerializerContract(name="Aliased")
        c.add_field(FieldDescriptor("judge_id", FieldType.INTEGER, alias="id"))
        result = c.serialize({"judge_id": 42})
        assert "id" in result
        assert result["id"] == 42

    def test_deserialize_reverses_alias(self):
        c = SerializerContract(name="Aliased")
        c.add_field(FieldDescriptor("judge_id", FieldType.INTEGER, alias="id"))
        result = c.deserialize({"id": 42})
        assert "judge_id" in result
        assert result["judge_id"] == 42

    def test_serialized_names(self):
        c = SerializerContract(name="S")
        c.add_field(FieldDescriptor("foo", FieldType.STRING, alias="bar"))
        assert "bar" in c.serialized_names()


# ---------------------------------------------------------------------------
# export_formats
# ---------------------------------------------------------------------------
from app.serializers.export_formats import (
    ExportFormat,
    ExportFormatRegistry,
    FormatDescriptor,
)


class TestExportFormats:
    def test_with_defaults_has_all_formats(self):
        reg = ExportFormatRegistry.with_defaults()
        for fmt in ExportFormat:
            assert reg.get(fmt) is not None

    def test_json_mime_type(self):
        reg = ExportFormatRegistry.with_defaults()
        desc = reg.get(ExportFormat.JSON)
        assert "json" in desc.mime_type

    def test_csv_is_streaming(self):
        reg = ExportFormatRegistry.with_defaults()
        desc = reg.get(ExportFormat.CSV)
        assert desc.streaming is True

    def test_negotiate_by_mime(self):
        reg = ExportFormatRegistry.with_defaults()
        result = reg.negotiate("application/json")
        assert result is not None
        assert result.fmt == ExportFormat.JSON

    def test_negotiate_unknown_returns_none(self):
        reg = ExportFormatRegistry.with_defaults()
        assert reg.negotiate("application/octet-stream") is None

    def test_from_extension(self):
        reg = ExportFormatRegistry.with_defaults()
        result = reg.from_extension("csv")
        assert result is not None
        assert result.fmt == ExportFormat.CSV

    def test_from_extension_with_dot(self):
        reg = ExportFormatRegistry.with_defaults()
        result = reg.from_extension(".json")
        assert result is not None
        assert result.fmt == ExportFormat.JSON

    def test_from_extension_unknown_returns_none(self):
        reg = ExportFormatRegistry.with_defaults()
        assert reg.from_extension("xyz") is None

    def test_streaming_formats_list(self):
        reg = ExportFormatRegistry.with_defaults()
        streaming = reg.streaming_formats()
        assert ExportFormat.JSONL in streaming or ExportFormat.CSV in streaming

    def test_supported_lists_registered_formats(self):
        reg = ExportFormatRegistry.with_defaults()
        assert len(reg.supported()) == len(ExportFormat)

    def test_unregister_removes_format(self):
        reg = ExportFormatRegistry.with_defaults()
        reg.unregister(ExportFormat.XML)
        assert reg.get(ExportFormat.XML) is None

    def test_register_custom_descriptor(self):
        reg = ExportFormatRegistry()
        desc = FormatDescriptor(
            fmt=ExportFormat.TEXT, mime_type="text/plain", extension="txt"
        )
        reg.register(desc)
        assert reg.get(ExportFormat.TEXT) == desc

    def test_accepts_mime_on_descriptor(self):
        desc = FormatDescriptor(
            fmt=ExportFormat.JSON, mime_type="application/json", extension="json"
        )
        assert desc.accepts_mime("application/json")
        assert not desc.accepts_mime("text/csv")


# ---------------------------------------------------------------------------
# schema_version
# ---------------------------------------------------------------------------
from app.serializers.schema_version import (
    SchemaVersion,
    SchemaVersionRegistry,
    VersionedSchema,
)


class TestSchemaVersion:
    def test_parse_three_parts(self):
        v = SchemaVersion.parse("2.3.1")
        assert (v.major, v.minor, v.patch) == (2, 3, 1)

    def test_parse_two_parts(self):
        v = SchemaVersion.parse("1.0")
        assert (v.major, v.minor, v.patch) == (1, 0, 0)

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError):
            SchemaVersion.parse("not.a.version")

    def test_str_representation(self):
        v = SchemaVersion(1, 2, 3)
        assert str(v) == "1.2.3"

    def test_comparison_less_than(self):
        assert SchemaVersion(1, 0, 0) < SchemaVersion(2, 0, 0)

    def test_comparison_greater_than(self):
        assert SchemaVersion(2, 0, 0) > SchemaVersion(1, 9, 9)

    def test_is_compatible_same_major_higher_minor(self):
        v1 = SchemaVersion(1, 5, 0)
        v2 = SchemaVersion(1, 3, 0)
        assert v1.is_compatible_with(v2)

    def test_is_compatible_same_major_lower_minor(self):
        v1 = SchemaVersion(1, 2, 0)
        v2 = SchemaVersion(1, 5, 0)
        assert not v1.is_compatible_with(v2)

    def test_is_breaking_different_major(self):
        assert SchemaVersion(2, 0, 0).is_breaking_from(SchemaVersion(1, 0, 0))

    def test_is_not_breaking_same_major(self):
        assert not SchemaVersion(1, 3, 0).is_breaking_from(SchemaVersion(1, 0, 0))

    def test_bump_major_resets_minor_and_patch(self):
        v = SchemaVersion(1, 2, 3).bump_major()
        assert v == SchemaVersion(2, 0, 0)

    def test_bump_minor_resets_patch(self):
        v = SchemaVersion(1, 2, 3).bump_minor()
        assert v == SchemaVersion(1, 3, 0)

    def test_bump_patch(self):
        v = SchemaVersion(1, 2, 3).bump_patch()
        assert v == SchemaVersion(1, 2, 4)


class TestSchemaVersionRegistry:
    def _registry(self) -> SchemaVersionRegistry:
        reg = SchemaVersionRegistry()
        reg.register(VersionedSchema("judge", SchemaVersion(1, 0, 0)))
        reg.register(VersionedSchema("judge", SchemaVersion(1, 1, 0)))
        reg.register(VersionedSchema("judge", SchemaVersion(2, 0, 0)))
        return reg

    def test_latest_returns_highest(self):
        reg = self._registry()
        vs = reg.latest("judge")
        assert vs is not None
        assert vs.version == SchemaVersion(2, 0, 0)

    def test_get_exact(self):
        reg = self._registry()
        vs = reg.get("judge", SchemaVersion(1, 1, 0))
        assert vs is not None
        assert vs.version == SchemaVersion(1, 1, 0)

    def test_get_missing_returns_none(self):
        reg = self._registry()
        assert reg.get("judge", SchemaVersion(9, 9, 9)) is None

    def test_register_duplicate_raises(self):
        reg = self._registry()
        with pytest.raises(ValueError):
            reg.register(VersionedSchema("judge", SchemaVersion(1, 0, 0)))

    def test_all_versions_sorted(self):
        reg = self._registry()
        versions = reg.all_versions("judge")
        version_nums = [vs.version for vs in versions]
        assert version_nums == sorted(version_nums)

    def test_deprecate_marks_schema(self):
        reg = self._registry()
        result = reg.deprecate("judge", SchemaVersion(1, 0, 0))
        assert result is True
        vs = reg.get("judge", SchemaVersion(1, 0, 0))
        assert vs.deprecated is True

    def test_deprecate_missing_returns_false(self):
        reg = self._registry()
        assert reg.deprecate("judge", SchemaVersion(9, 0, 0)) is False

    def test_negotiate_skips_deprecated(self):
        reg = self._registry()
        reg.deprecate("judge", SchemaVersion(2, 0, 0))
        best = reg.negotiate("judge", SchemaVersion(2, 0, 0))
        # should fall back to a non-deprecated version in the same major or lower
        assert best is None or not best.deprecated


# ---------------------------------------------------------------------------
# field_filters
# ---------------------------------------------------------------------------
from app.serializers.field_filters import (
    FieldFilterPipeline,
    FieldMask,
    FieldRedactor,
    FieldTransformer,
)


class TestFieldMask:
    def test_from_list(self):
        mask = FieldMask.from_list(["a", "b"])
        assert mask.includes("a")
        assert not mask.includes("c")

    def test_excludes(self):
        mask = FieldMask.from_list(["a"])
        assert mask.excludes("b")

    def test_apply_filters_keys(self):
        mask = FieldMask.from_list(["name"])
        result = mask.apply({"name": "Alice", "secret": "xyz"})
        assert "name" in result
        assert "secret" not in result

    def test_apply_empty_mask_returns_nothing(self):
        mask = FieldMask.from_list([])
        assert mask.apply({"a": 1}) == {}

    def test_intersect(self):
        m1 = FieldMask.from_list(["a", "b", "c"])
        m2 = FieldMask.from_list(["b", "c", "d"])
        inter = m1.intersect(m2)
        assert inter.includes("b") and inter.includes("c")
        assert not inter.includes("a") and not inter.includes("d")

    def test_union(self):
        m1 = FieldMask.from_list(["a"])
        m2 = FieldMask.from_list(["b"])
        union = m1.union(m2)
        assert union.includes("a") and union.includes("b")

    def test_len(self):
        mask = FieldMask.from_list(["x", "y"])
        assert len(mask) == 2


class TestFieldRedactor:
    def test_redact_sensitive_field(self):
        r = FieldRedactor(sensitive_fields={"password"})
        result = r.redact({"username": "alice", "password": "s3cr3t"})
        assert result["password"] == r.placeholder
        assert result["username"] == "alice"

    def test_add_field(self):
        r = FieldRedactor()
        r.add("ssn")
        assert r.is_sensitive("ssn")

    def test_remove_field(self):
        r = FieldRedactor(sensitive_fields={"ssn"})
        r.remove("ssn")
        assert not r.is_sensitive("ssn")

    def test_non_sensitive_untouched(self):
        r = FieldRedactor(sensitive_fields={"pw"})
        result = r.redact({"email": "a@b.com"})
        assert result["email"] == "a@b.com"

    def test_custom_placeholder(self):
        r = FieldRedactor(sensitive_fields={"pw"}, placeholder="***")
        result = r.redact({"pw": "abc"})
        assert result["pw"] == "***"


class TestFieldTransformer:
    def test_register_and_apply(self):
        t = FieldTransformer()
        t.register("score", lambda v: round(float(v), 2))
        result = t.apply({"score": "3.14159", "name": "x"})
        assert result["score"] == pytest.approx(3.14)

    def test_unregistered_field_unchanged(self):
        t = FieldTransformer()
        result = t.apply({"name": "alice"})
        assert result["name"] == "alice"

    def test_unregister(self):
        t = FieldTransformer()
        t.register("x", str.upper)
        t.unregister("x")
        assert not t.has_transform("x")

    def test_registered_fields_list(self):
        t = FieldTransformer()
        t.register("b", str)
        t.register("a", str)
        assert t.registered_fields == ["a", "b"]


class TestFieldFilterPipeline:
    def test_mask_then_redact_then_transform(self):
        mask = FieldMask.from_list(["name", "score", "secret"])
        redactor = FieldRedactor(sensitive_fields={"secret"})
        transformer = FieldTransformer()
        transformer.register("name", str.upper)
        pipeline = FieldFilterPipeline(
            mask=mask, redactor=redactor, transformer=transformer
        )
        result = pipeline.apply(
            {"name": "alice", "score": 9, "secret": "xyz", "extra": 1}
        )
        assert result["name"] == "ALICE"
        assert result["secret"] == redactor.placeholder
        assert "extra" not in result

    def test_no_mask_passes_all(self):
        redactor = FieldRedactor(sensitive_fields={"pw"})
        pipeline = FieldFilterPipeline(redactor=redactor)
        result = pipeline.apply({"user": "bob", "pw": "secret"})
        assert "user" in result
        assert result["pw"] == redactor.placeholder


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------
from app.serializers.pagination import Cursor, Page, PageMeta, PageRequest, PageStrategy


class TestPageRequest:
    def test_default_offset_strategy(self):
        r = PageRequest()
        assert r.strategy == PageStrategy.OFFSET

    def test_offset_calculation(self):
        r = PageRequest(page=3, page_size=10)
        assert r.offset == 20

    def test_page_one_offset_zero(self):
        r = PageRequest(page=1, page_size=25)
        assert r.offset == 0

    def test_next_page(self):
        r = PageRequest(page=2)
        nxt = r.next_page()
        assert nxt.page == 3

    def test_prev_page_returns_none_on_page_one(self):
        r = PageRequest(page=1)
        assert r.prev_page() is None

    def test_prev_page(self):
        r = PageRequest(page=4)
        prev = r.prev_page()
        assert prev.page == 3

    def test_invalid_page_raises(self):
        with pytest.raises(ValueError):
            PageRequest(page=0)

    def test_invalid_page_size_raises(self):
        with pytest.raises(ValueError):
            PageRequest(page_size=0)


class TestCursor:
    def test_encode_decode_roundtrip(self):
        c = Cursor(payload={"id": 42, "ts": "2024-01-01"})
        token = c.encode()
        d = Cursor.decode(token)
        assert d.get("id") == 42
        assert d.get("ts") == "2024-01-01"

    def test_decode_bad_token_raises(self):
        with pytest.raises(ValueError):
            Cursor.decode("not-valid-base64!!!")

    def test_set_and_get(self):
        c = Cursor()
        c.set("page", 5)
        assert c.get("page") == 5

    def test_get_missing_returns_default(self):
        c = Cursor()
        assert c.get("missing", "fallback") == "fallback"

    def test_token_is_url_safe(self):
        c = Cursor(payload={"k": "v" * 50})
        token = c.encode()
        assert "+" not in token
        assert "/" not in token


class TestPageMeta:
    def test_for_offset_classmethod(self):
        meta = PageMeta.for_offset(page=2, page_size=10, total_items=25)
        assert meta.page == 2
        assert meta.has_next is True
        assert meta.has_prev is True

    def test_total_pages_calculated(self):
        meta = PageMeta.for_offset(page=1, page_size=10, total_items=25)
        assert meta.total_pages == 3

    def test_total_pages_none_when_no_total(self):
        meta = PageMeta(
            page=1, page_size=10, total_items=None, has_next=True, has_prev=False
        )
        assert meta.total_pages is None

    def test_last_page_has_no_next(self):
        meta = PageMeta.for_offset(page=3, page_size=10, total_items=25)
        assert meta.has_next is False

    def test_first_page_has_no_prev(self):
        meta = PageMeta.for_offset(page=1, page_size=10, total_items=25)
        assert meta.has_prev is False

    def test_as_dict_keys(self):
        meta = PageMeta.for_offset(page=1, page_size=10, total_items=30)
        d = meta.as_dict()
        assert "page" in d
        assert "page_size" in d
        assert "total_pages" in d


class TestPage:
    def test_len(self):
        meta = PageMeta.for_offset(1, 10, 3)
        p: Page[int] = Page(items=[1, 2, 3], meta=meta)
        assert len(p) == 3

    def test_is_empty_true(self):
        meta = PageMeta.for_offset(1, 10, 0)
        p: Page[int] = Page(items=[], meta=meta)
        assert p.is_empty()

    def test_is_empty_false(self):
        meta = PageMeta.for_offset(1, 10, 1)
        p: Page[str] = Page(items=["x"], meta=meta)
        assert not p.is_empty()

    def test_as_dict_contains_items_and_meta(self):
        meta = PageMeta.for_offset(1, 10, 2)
        p = Page(items=["a", "b"], meta=meta)
        d = p.as_dict()
        assert "items" in d
        assert "meta" in d


# ---------------------------------------------------------------------------
# validation_report
# ---------------------------------------------------------------------------
from app.serializers.validation_report import (
    Severity,
    ValidationIssue,
    ValidationReport,
)


class TestValidationIssue:
    def test_defaults_to_error_severity(self):
        issue = ValidationIssue(field_path="name", message="required")
        assert issue.severity == Severity.ERROR
        assert issue.is_error()
        assert not issue.is_warning()

    def test_warning_severity(self):
        issue = ValidationIssue(
            field_path="notes", message="too long", severity=Severity.WARNING
        )
        assert issue.is_warning()
        assert not issue.is_error()

    def test_as_dict_keys(self):
        issue = ValidationIssue(field_path="x", message="bad", code="E001")
        d = issue.as_dict()
        assert "field_path" in d
        assert "message" in d
        assert "severity" in d
        assert d["code"] == "E001"


class TestValidationReport:
    def test_empty_report_is_valid(self):
        r = ValidationReport()
        assert r.is_valid()

    def test_adding_error_makes_invalid(self):
        r = ValidationReport()
        r.error("name", "required")
        assert not r.is_valid()

    def test_adding_warning_stays_valid(self):
        r = ValidationReport()
        r.warning("notes", "too long")
        assert r.is_valid()

    def test_error_count(self):
        r = ValidationReport()
        r.error("a", "e1")
        r.error("b", "e2")
        r.warning("c", "w1")
        assert r.error_count == 2
        assert r.warning_count == 1

    def test_total_count(self):
        r = ValidationReport()
        r.error("a", "e")
        r.info("b", "i")
        assert r.total_count == 2

    def test_errors_list(self):
        r = ValidationReport()
        r.error("x", "bad")
        r.warning("y", "warn")
        assert len(r.errors()) == 1
        assert r.errors()[0].field_path == "x"

    def test_warnings_list(self):
        r = ValidationReport()
        r.warning("y", "warn")
        r.info("z", "note")
        assert len(r.warnings()) == 1

    def test_field_errors_filter(self):
        r = ValidationReport()
        r.error("email", "invalid format")
        r.error("name", "required")
        assert len(r.field_errors("email")) == 1
        assert r.has_field_error("email")
        assert not r.has_field_error("phone")

    def test_unique_error_fields(self):
        r = ValidationReport()
        r.error("email", "msg1")
        r.error("email", "msg2")
        r.error("name", "required")
        fields = r.unique_error_fields()
        assert len(fields) == 2
        assert "email" in fields

    def test_as_dict_structure(self):
        r = ValidationReport(subject="JudgeForm")
        r.error("field", "bad")
        d = r.as_dict()
        assert d["valid"] is False
        assert d["error_count"] == 1
        assert d["subject"] == "JudgeForm"
        assert isinstance(d["issues"], list)

    def test_merge_combines_issues(self):
        r1 = ValidationReport()
        r1.error("a", "err")
        r2 = ValidationReport()
        r2.warning("b", "warn")
        r1.merge(r2)
        assert r1.total_count == 2
        assert r1.error_count == 1

    def test_clear_removes_all_issues(self):
        r = ValidationReport()
        r.error("x", "bad")
        r.clear()
        assert r.total_count == 0
        assert r.is_valid()

    def test_add_with_code(self):
        r = ValidationReport()
        r.error("ssn", "invalid", code="SSN_001")
        issues = r.errors()
        assert issues[0].code == "SSN_001"

    def test_info_is_recorded(self):
        r = ValidationReport()
        r.info("notes", "truncated to 500 chars")
        assert r.total_count == 1
        assert r.is_valid()  # info doesn't affect validity
