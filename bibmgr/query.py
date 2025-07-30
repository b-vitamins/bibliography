"""Query builder and filtering for bibliography entries."""

import re
from collections.abc import Callable
from typing import Any

from .models import BibEntry


class Query:
    """Build and execute queries on bibliography entries."""

    def __init__(self, entries: list[BibEntry]) -> None:
        """Initialize query with entries."""
        self._entries = entries
        self._filters: list[Callable[[BibEntry], bool]] = []
        self._sort_key: Callable[[BibEntry], Any] | None = None
        self._sort_reverse = False
        self._limit: int | None = None

    def where(self, field: str, value: str, exact: bool = True) -> "Query":
        """Filter entries by field value."""
        if exact:
            self._filters.append(lambda e: e.fields.get(field, "") == value)
        else:
            # Case-insensitive partial match
            pattern = re.compile(re.escape(value), re.IGNORECASE)
            self._filters.append(
                lambda e: bool(pattern.search(e.fields.get(field, "")))
            )
        return self

    def where_type(self, entry_type: str) -> "Query":
        """Filter entries by type."""
        self._filters.append(lambda e: e.entry_type == entry_type)
        return self

    def where_key(self, pattern: str) -> "Query":
        """Filter entries by key pattern."""
        regex = re.compile(pattern, re.IGNORECASE)
        self._filters.append(lambda e: bool(regex.search(e.key)))
        return self

    def where_any(self, value: str) -> "Query":
        """Filter entries where any field contains value."""
        pattern = re.compile(re.escape(value), re.IGNORECASE)

        def match_any(entry: BibEntry) -> bool:
            # Check key
            if pattern.search(entry.key):
                return True
            # Check all fields
            for field_value in entry.fields.values():
                if pattern.search(field_value):
                    return True
            return False

        self._filters.append(match_any)
        return self

    def where_has(self, field: str) -> "Query":
        """Filter entries that have a specific field."""
        self._filters.append(lambda e: field in e.fields)
        return self

    def where_missing(self, field: str) -> "Query":
        """Filter entries missing a specific field."""
        self._filters.append(lambda e: field not in e.fields)
        return self

    def where_custom(self, predicate: Callable[[BibEntry], bool]) -> "Query":
        """Add custom filter predicate."""
        self._filters.append(predicate)
        return self

    def order_by(self, field: str, reverse: bool = False) -> "Query":
        """Sort results by field value."""
        self._sort_key = lambda e: e.fields.get(field, "")
        self._sort_reverse = reverse
        return self

    def order_by_key(self, reverse: bool = False) -> "Query":
        """Sort results by entry key."""
        self._sort_key = lambda e: e.key
        self._sort_reverse = reverse
        return self

    def order_by_type(self, reverse: bool = False) -> "Query":
        """Sort results by entry type."""
        self._sort_key = lambda e: e.entry_type
        self._sort_reverse = reverse
        return self

    def limit(self, n: int) -> "Query":
        """Limit number of results."""
        self._limit = n
        return self

    def execute(self) -> list[BibEntry]:
        """Execute query and return results."""
        # Apply filters
        results = self._entries
        for filter_func in self._filters:
            results = [e for e in results if filter_func(e)]

        # Apply sorting
        if self._sort_key:
            results = sorted(results, key=self._sort_key, reverse=self._sort_reverse)

        # Apply limit
        if self._limit is not None:
            results = results[: self._limit]

        return results

    def count(self) -> int:
        """Count matching entries without limit."""
        # Apply filters but not limit
        results = self._entries
        for filter_func in self._filters:
            results = [e for e in results if filter_func(e)]
        return len(results)

    def first(self) -> BibEntry | None:
        """Get first matching entry."""
        results = self.limit(1).execute()
        return results[0] if results else None

    def exists(self) -> bool:
        """Check if any entries match."""
        return self.count() > 0


class QueryBuilder:
    """Fluent interface for building queries."""

    def __init__(self, entries: list[BibEntry]) -> None:
        """Initialize with entries."""
        self._entries = entries

    def all(self) -> Query:
        """Create query matching all entries."""
        return Query(self._entries)

    def by_type(self, entry_type: str) -> Query:
        """Create query filtering by type."""
        return Query(self._entries).where_type(entry_type)

    def by_author(self, author: str, exact: bool = False) -> Query:
        """Create query filtering by author."""
        return Query(self._entries).where("author", author, exact=exact)

    def by_year(self, year: str | int) -> Query:
        """Create query filtering by year."""
        return Query(self._entries).where("year", str(year))

    def by_title(self, title: str, exact: bool = False) -> Query:
        """Create query filtering by title."""
        return Query(self._entries).where("title", title, exact=exact)

    def search(self, query: str) -> Query:
        """Create query searching all fields."""
        return Query(self._entries).where_any(query)

    def missing_field(self, field: str) -> Query:
        """Create query for entries missing a field."""
        return Query(self._entries).where_missing(field)

    def has_field(self, field: str) -> Query:
        """Create query for entries having a field."""
        return Query(self._entries).where_has(field)
