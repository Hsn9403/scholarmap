#!/usr/bin/env python3
"""
Export utilities for generating reports (Excel, CSV).

This module provides:
- ExcelExporter: Class for generating styled Excel dashboards
- write_xlsx: Backward-compatible function for Excel export

Example:
    >>> from src.export import ExcelExporter
    >>> exporter = ExcelExporter()
    >>> exporter.write("report.xlsx", "Marie Curie", scholar_data, patents_data)
"""
from .excel import ExcelExporter, write_xlsx

__all__ = [
    "ExcelExporter",
    "write_xlsx",
]
