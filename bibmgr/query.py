"""Query parsing and building for FTS5 search.

This module handles converting user queries into FTS5-compatible syntax
and provides query building utilities.
"""

import re


class QueryBuilder:
    """Builds FTS5 queries from user input."""

    # Valid FTS5 column names
    FTS_COLUMNS = {"key", "title", "author", "abstract", "keywords", "journal", "year"}

    # Query operators that FTS5 supports
    FTS_OPERATORS = {"AND", "OR", "NOT", "NEAR"}

    def __init__(self):
        """Initialize query builder."""
        self.warnings: list[str] = []

    def build_query(self, user_query: str) -> str:
        """Build FTS5 query from user input.

        Args:
            user_query: User's search query

        Returns:
            FTS5-compatible query string
        """
        self.warnings.clear()

        if not user_query or not user_query.strip():
            return ""

        # Clean and normalize the query
        query = self._normalize_query(user_query)

        # Handle different query types
        if self._is_field_query(query):
            return self._build_field_query(query)
        elif self._is_boolean_query(query):
            return self._build_boolean_query(query)
        elif self._is_phrase_query(query):
            return self._build_phrase_query(query)
        elif self._has_wildcards(query):
            return self._build_wildcard_query(query)
        else:
            return self._build_simple_query(query)

    def get_warnings(self) -> list[str]:
        """Get any warnings from query building.

        Returns:
            List of warning messages
        """
        return self.warnings.copy()

    def _normalize_query(self, query: str) -> str:
        """Normalize query string.

        Args:
            query: Raw query string

        Returns:
            Normalized query string
        """
        # Remove extra whitespace
        query = re.sub(r"\s+", " ", query.strip())

        # Normalize boolean operators to uppercase
        for op in self.FTS_OPERATORS:
            query = re.sub(f"\\b{op.lower()}\\b", op, query, flags=re.IGNORECASE)

        return query

    def _is_field_query(self, query: str) -> bool:
        """Check if query contains field specifications.

        Args:
            query: Query string

        Returns:
            True if query has field specifications
        """
        return ":" in query and bool(re.search(r"\w+:", query))

    def _is_boolean_query(self, query: str) -> bool:
        """Check if query contains boolean operators.

        Args:
            query: Query string

        Returns:
            True if query has boolean operators
        """
        return any(op in query for op in self.FTS_OPERATORS)

    def _is_phrase_query(self, query: str) -> bool:
        """Check if query is a phrase query.

        Args:
            query: Query string

        Returns:
            True if query is enclosed in quotes
        """
        return query.startswith('"') and query.endswith('"') and len(query) > 2

    def _has_wildcards(self, query: str) -> bool:
        """Check if query contains wildcards.

        Args:
            query: Query string

        Returns:
            True if query has wildcard characters
        """
        return "*" in query or "?" in query

    def _build_field_query(self, query: str) -> str:
        """Build field-specific query.

        Args:
            query: Query with field specifications

        Returns:
            FTS5 field query
        """
        # Pattern to match field:value pairs
        field_pattern = r"(\w+):([^\s]+|\".+?\")"

        def replace_field(match: re.Match[str]) -> str:
            field = match.group(1).lower()
            value = match.group(2)

            if field in self.FTS_COLUMNS:
                # Use FTS5 column syntax
                return f"{{{field}}}:{value}"
            else:
                self.warnings.append(
                    f"Unknown field '{field}', searching in all fields"
                )
                return value

        # Replace field specifications
        fts_query = re.sub(field_pattern, replace_field, query)

        return fts_query

    def _build_boolean_query(self, query: str) -> str:
        """Build boolean query.

        Args:
            query: Query with boolean operators

        Returns:
            FTS5 boolean query
        """
        # FTS5 supports boolean operators natively
        # Just need to handle field specifications within boolean expressions

        if self._is_field_query(query):
            # Handle field queries within boolean context
            return self._build_field_query(query)

        return query

    def _build_phrase_query(self, query: str) -> str:
        """Build phrase query.

        Args:
            query: Quoted phrase query

        Returns:
            FTS5 phrase query
        """
        # FTS5 handles quoted phrases natively
        return query

    def _build_wildcard_query(self, query: str) -> str:
        """Build wildcard query.

        Args:
            query: Query with wildcards

        Returns:
            FTS5 wildcard query
        """
        # FTS5 supports * wildcard at end of terms
        # Convert ? to * for FTS5 compatibility
        query = query.replace("?", "*")

        # Warn about unsupported wildcard patterns
        if "*" in query[:-1]:  # Wildcard not at end
            parts = query.split()
            for part in parts:
                if "*" in part and not part.endswith("*"):
                    self.warnings.append(
                        f"FTS5 only supports trailing wildcards, '{part}' may not work "
                        f"as expected"
                    )

        return query

    def _build_simple_query(self, query: str) -> str:
        """Build simple query.

        Args:
            query: Simple text query

        Returns:
            FTS5 simple query
        """
        # For simple queries, FTS5 handles them as-is
        return query


def parse_query(user_query: str) -> tuple[str, list[str]]:
    """Parse user query into FTS5 format.

    Args:
        user_query: User's search query

    Returns:
        Tuple of (fts5_query, warnings)
    """
    builder = QueryBuilder()
    fts5_query = builder.build_query(user_query)
    warnings = builder.get_warnings()

    return fts5_query, warnings
