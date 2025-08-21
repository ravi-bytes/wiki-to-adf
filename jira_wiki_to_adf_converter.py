#!/usr/bin/env python3
"""
Jira Wiki Markup to ADF (Atlassian Document Format) Converter

This module provides comprehensive conversion from Jira Wiki Markup to ADF format
with robust error handling, logging, and support for all Jira Wiki Markup elements.

Usage:
    python jira_wiki_to_adf.py input_file.txt
    
    or
    
    from jira_wiki_to_adf import JiraWikiToADFConverter
    converter = JiraWikiToADFConverter()
    converter.convert_file('input.txt')
"""

import re
import json
import os
import sys
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import logging
from pathlib import Path


class ParseErrorType(Enum):
    """Types of parsing errors that can occur."""
    MALFORMED_TABLE = "malformed_table"
    UNCLOSED_TAG = "unclosed_tag"
    INVALID_HEADING = "invalid_heading"
    MALFORMED_LINK = "malformed_link"
    INVALID_COLOR = "invalid_color"
    NESTED_FORMATTING = "nested_formatting"
    UNKNOWN_MACRO = "unknown_macro"
    INVALID_LIST = "invalid_list"


@dataclass
class ParseError:
    """Represents a parsing error with context."""
    error_type: ParseErrorType
    line_number: int
    column: int
    original_text: str
    parsed_as: str
    message: str


@dataclass
class ParsingContext:
    """Context for parsing operations."""
    errors: List[ParseError] = field(default_factory=list)
    line_number: int = 1
    in_table: bool = False
    in_list: bool = False
    list_stack: List[str] = field(default_factory=list)
    in_code_block: bool = False
    code_block_type: Optional[str] = None


class JiraWikiToADFConverter:
    """
    Converts Jira Wiki Markup to ADF (Atlassian Document Format).
    
    Supports all major Jira Wiki Markup elements with comprehensive error handling.
    """
    
    def __init__(self, enable_logging: bool = True):
        """
        Initialize the converter.
        
        Args:
            enable_logging: Whether to enable detailed logging
        """
        self.enable_logging = enable_logging
        self.context = ParsingContext()
        self.logger = self._setup_logger()
        
        # Compile regex patterns for better performance
        self._compile_patterns()
    
    def _setup_logger(self) -> logging.Logger:
        """Set up logging configuration."""
        logger = logging.getLogger('JiraWikiToADF')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        logger.setLevel(logging.INFO if self.enable_logging else logging.WARNING)
        return logger
    
    def _compile_patterns(self):
        """Compile regex patterns for performance."""
        # Text formatting patterns
        self.patterns = {
            'heading': re.compile(r'^h([1-6])\.\s*(.+)$', re.MULTILINE),
            'bold': re.compile(r'\*([^*\n]+)\*'),
            'italic': re.compile(r'_([^_\n]+)_'),
            'underline': re.compile(r'\+([^+\n]+)\+'),
            'strikethrough': re.compile(r'-([^-\n]+)-'),
            'superscript': re.compile(r'\^([^^^\n]+)\^'),
            'subscript': re.compile(r'~([^~\n]+)~'),
            'monospace': re.compile(r'\{\{([^}]+)\}\}'),
            'citation': re.compile(r'\?\?([^?\n]+)\?\?'),
            'color': re.compile(r'\{color:(#?[a-fA-F0-9]{3,6}|[a-zA-Z]+)\}(.*?)\{color\}', re.DOTALL),
            'link_with_text': re.compile(r'\[([^|\]]+)\|([^\]]+)\]'),
            'link_simple': re.compile(r'\[([^\]]+)\]'),
            'image': re.compile(r'!([^!\n]+)!'),
            'table_header': re.compile(r'^\|\|(.+)\|\|$'),
            'table_row': re.compile(r'^\|([^|].+[^|])\|$'),
            'bullet_list': re.compile(r'^(\*+)\s+(.+)$'),
            'numbered_list': re.compile(r'^(#+)\s+(.+)$'),
            'horizontal_rule': re.compile(r'^----+$'),
            'line_break': re.compile(r'\\\\'),
            'code_block': re.compile(r'\{code(?::([a-zA-Z0-9]+))?\}(.*?)\{code\}', re.DOTALL),
            'noformat': re.compile(r'\{noformat\}(.*?)\{noformat\}', re.DOTALL),
            'quote': re.compile(r'\{quote\}(.*?)\{quote\}', re.DOTALL),
            'panel': re.compile(r'\{panel(?::title=([^}]*))?\}(.*?)\{panel\}', re.DOTALL),
            'toc': re.compile(r'\{toc(?::([^}]*))?\}'),
            'anchor': re.compile(r'\{anchor:([^}]+)\}'),
        }
    
    def convert_file(self, input_file: str) -> str:
        """
        Convert a Jira Wiki Markup file to ADF format.
        
        Args:
            input_file: Path to input file
            
        Returns:
            Path to output file
            
        Raises:
            FileNotFoundError: If input file doesn't exist
            IOError: If file operations fail
        """
        input_path = Path(input_file)
        
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_file}")
        
        # Generate output filename
        output_file = str(input_path.with_name(f"{input_path.stem}-adf.txt"))
        
        self.logger.info(f"Converting {input_file} to {output_file}")
        
        try:
            # Read input file
            with open(input_file, 'r', encoding='utf-8') as f:
                wiki_content = f.read()
            
            # Convert to ADF
            adf_content = self.convert_text(wiki_content)
            
            # Write output file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(adf_content, f, indent=2, ensure_ascii=False)
            
            # Log results
            self._log_conversion_results(input_file, output_file)
            
            return output_file
            
        except IOError as e:
            self.logger.error(f"File operation failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Conversion failed: {e}")
            raise
    
    def convert_text(self, wiki_text: str) -> Dict[str, Any]:
        """
        Convert Jira Wiki Markup text to ADF format.
        
        Args:
            wiki_text: Wiki markup text
            
        Returns:
            ADF document as dictionary
        """
        # Reset context for new conversion
        self.context = ParsingContext()
        
        # Normalize line endings
        wiki_text = wiki_text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Convert to ADF
        content = self._parse_document(wiki_text)
        
        # Create ADF document structure
        adf_doc = {
            "version": 1,
            "type": "doc",
            "content": content
        }
        
        return adf_doc
    
    def _parse_document(self, text: str) -> List[Dict[str, Any]]:
        """Parse the entire document into ADF content."""
        lines = text.split('\n')
        content = []
        i = 0
        
        while i < len(lines):
            self.context.line_number = i + 1
            line = lines[i]
            
            # Skip empty lines at document level
            if not line.strip():
                i += 1
                continue
            
            # Check for block-level elements
            block_result = self._parse_block_element(lines, i)
            if block_result:
                element, lines_consumed = block_result
                content.append(element)
                i += lines_consumed
            else:
                # Parse as paragraph
                paragraph, lines_consumed = self._parse_paragraph(lines, i)
                if paragraph:
                    content.append(paragraph)
                i += lines_consumed
        
        return content if content else [self._create_empty_paragraph()]
    
    def _parse_block_element(self, lines: List[str], start_idx: int) -> Optional[Tuple[Dict[str, Any], int]]:
        """Parse block-level elements."""
        line = lines[start_idx].strip()
        
        # Headings
        heading_match = self.patterns['heading'].match(line)
        if heading_match:
            level = int(heading_match.group(1))
            text = heading_match.group(2).strip()
            
            return {
                "type": "heading",
                "attrs": {"level": level},
                "content": self._parse_inline_content(text)
            }, 1
        
        # Horizontal rule
        if self.patterns['horizontal_rule'].match(line):
            return {"type": "rule"}, 1
        
        # Tables
        if self.patterns['table_header'].match(line) or self.patterns['table_row'].match(line):
            return self._parse_table(lines, start_idx)
        
        # Lists
        if self.patterns['bullet_list'].match(line) or self.patterns['numbered_list'].match(line):
            return self._parse_list(lines, start_idx)
        
        # Code blocks
        code_match = self.patterns['code_block'].search('\n'.join(lines[start_idx:]))
        if code_match and code_match.start() == 0:
            return self._parse_code_block_from_match(code_match), code_match.group(0).count('\n') + 1
        
        # Noformat blocks
        noformat_match = self.patterns['noformat'].search('\n'.join(lines[start_idx:]))
        if noformat_match and noformat_match.start() == 0:
            return self._parse_noformat_block(noformat_match), noformat_match.group(0).count('\n') + 1
        
        # Quotes
        quote_match = self.patterns['quote'].search('\n'.join(lines[start_idx:]))
        if quote_match and quote_match.start() == 0:
            return self._parse_quote_block(quote_match), quote_match.group(0).count('\n') + 1
        
        # Panels
        panel_match = self.patterns['panel'].search('\n'.join(lines[start_idx:]))
        if panel_match and panel_match.start() == 0:
            return self._parse_panel_block(panel_match), panel_match.group(0).count('\n') + 1
        
        return None
    
    def _parse_paragraph(self, lines: List[str], start_idx: int) -> Tuple[Optional[Dict[str, Any]], int]:
        """Parse a paragraph, consuming lines until empty line or block element."""
        paragraph_lines = []
        i = start_idx
        
        while i < len(lines):
            line = lines[i]
            
            # Stop at empty line
            if not line.strip():
                break
            
            # Stop if we hit a block element
            if self._is_block_element_start(line):
                if i > start_idx:  # Only stop if we've collected some content
                    break
            
            paragraph_lines.append(line)
            i += 1
        
        if not paragraph_lines:
            return None, 1
        
        # Join lines and parse inline content
        paragraph_text = '\n'.join(paragraph_lines)
        content = self._parse_inline_content(paragraph_text)
        
        if not content:
            return self._create_empty_paragraph(), len(paragraph_lines)
        
        return {
            "type": "paragraph",
            "content": content
        }, len(paragraph_lines)
    
    def _is_block_element_start(self, line: str) -> bool:
        """Check if line starts a block element."""
        line = line.strip()
        
        # Check various block element patterns
        patterns_to_check = [
            self.patterns['heading'],
            self.patterns['table_header'],
            self.patterns['table_row'],
            self.patterns['bullet_list'],
            self.patterns['numbered_list'],
            self.patterns['horizontal_rule']
        ]
        
        for pattern in patterns_to_check:
            if pattern.match(line):
                return True
        
        # Check for macro starts
        if line.startswith('{code') or line.startswith('{noformat') or line.startswith('{quote') or line.startswith('{panel'):
            return True
        
        return False
    
    def _parse_table(self, lines: List[str], start_idx: int) -> Tuple[Dict[str, Any], int]:
        """Parse a table structure."""
        table_rows = []
        i = start_idx
        
        try:
            while i < len(lines):
                line = lines[i].strip()
                
                # Table header row
                header_match = self.patterns['table_header'].match(line)
                if header_match:
                    cells = [cell.strip() for cell in header_match.group(1).split('||')]
                    table_row = {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "content": [{"type": "paragraph", "content": self._parse_inline_content(cell)}]
                            }
                            for cell in cells if cell
                        ]
                    }
                    table_rows.append(table_row)
                    i += 1
                    continue
                
                # Table data row
                row_match = self.patterns['table_row'].match(line)
                if row_match:
                    cells = [cell.strip() for cell in row_match.group(1).split('|')]
                    table_row = {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [{"type": "paragraph", "content": self._parse_inline_content(cell)}]
                            }
                            for cell in cells if cell
                        ]
                    }
                    table_rows.append(table_row)
                    i += 1
                    continue
                
                # End of table
                break
            
        except Exception as e:
            self._add_error(
                ParseErrorType.MALFORMED_TABLE,
                self.context.line_number,
                0,
                lines[start_idx] if start_idx < len(lines) else "",
                "Converted to paragraph",
                f"Table parsing failed: {e}"
            )
            # Fallback to paragraph
            return self._parse_paragraph(lines, start_idx)
        
        if not table_rows:
            return self._parse_paragraph(lines, start_idx)
        
        return {
            "type": "table",
            "content": table_rows
        }, i - start_idx
    
    def _parse_list(self, lines: List[str], start_idx: int) -> Tuple[Dict[str, Any], int]:
        """Parse list structures (bullet or numbered)."""
        list_items = []
        i = start_idx
        list_type = None
        
        while i < len(lines):
            line = lines[i]
            
            # Check for bullet list item
            bullet_match = self.patterns['bullet_list'].match(line)
            if bullet_match:
                if list_type is None:
                    list_type = "bulletList"
                elif list_type != "bulletList":
                    break  # Different list type, end current list
                
                level = len(bullet_match.group(1))
                content = bullet_match.group(2)
                
                list_item = {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": self._parse_inline_content(content)}]
                }
                list_items.append(list_item)
                i += 1
                continue
            
            # Check for numbered list item
            numbered_match = self.patterns['numbered_list'].match(line)
            if numbered_match:
                if list_type is None:
                    list_type = "orderedList"
                elif list_type != "orderedList":
                    break  # Different list type, end current list
                
                level = len(numbered_match.group(1))
                content = numbered_match.group(2)
                
                list_item = {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": self._parse_inline_content(content)}]
                }
                list_items.append(list_item)
                i += 1
                continue
            
            # End of list
            if line.strip():  # Non-empty line that's not a list item
                break
            i += 1  # Skip empty lines within list
        
        if not list_items:
            return self._parse_paragraph(lines, start_idx)
        
        return {
            "type": list_type or "bulletList",
            "content": list_items
        }, i - start_idx
    
    def _parse_code_block_from_match(self, match: re.Match) -> Dict[str, Any]:
        """Parse code block from regex match."""
        language = match.group(1) or ""
        code_content = match.group(2).strip()
        
        attrs = {}
        if language:
            attrs["language"] = language
        
        return {
            "type": "codeBlock",
            "attrs": attrs,
            "content": [{"type": "text", "text": code_content}]
        }
    
    def _parse_noformat_block(self, match: re.Match) -> Dict[str, Any]:
        """Parse noformat block."""
        content = match.group(1)
        
        return {
            "type": "codeBlock",
            "content": [{"type": "text", "text": content}]
        }
    
    def _parse_quote_block(self, match: re.Match) -> Dict[str, Any]:
        """Parse quote block."""
        content = match.group(1).strip()
        
        return {
            "type": "blockquote",
            "content": [{"type": "paragraph", "content": self._parse_inline_content(content)}]
        }
    
    def _parse_panel_block(self, match: re.Match) -> Dict[str, Any]:
        """Parse panel block."""
        title = match.group(1)
        content = match.group(2).strip()
        
        attrs = {}
        if title:
            attrs["title"] = title
        
        return {
            "type": "panel",
            "attrs": attrs,
            "content": [{"type": "paragraph", "content": self._parse_inline_content(content)}]
        }
    
    def _parse_inline_content(self, text: str) -> List[Dict[str, Any]]:
        """Parse inline content with formatting."""
        if not text.strip():
            return []
        
        # Process text in order of precedence
        content = []
        remaining_text = text
        
        while remaining_text:
            # Find the earliest match among all inline patterns
            earliest_match = None
            earliest_pos = len(remaining_text)
            pattern_name = None
            
            inline_patterns = [
                ('color', self.patterns['color']),
                ('link_with_text', self.patterns['link_with_text']),
                ('link_simple', self.patterns['link_simple']),
                ('image', self.patterns['image']),
                ('code_block', self.patterns['code_block']),
                ('noformat', self.patterns['noformat']),
                ('quote', self.patterns['quote']),
                ('monospace', self.patterns['monospace']),
                ('bold', self.patterns['bold']),
                ('italic', self.patterns['italic']),
                ('underline', self.patterns['underline']),
                ('strikethrough', self.patterns['strikethrough']),
                ('superscript', self.patterns['superscript']),
                ('subscript', self.patterns['subscript']),
                ('citation', self.patterns['citation']),
                ('line_break', self.patterns['line_break']),
            ]
            
            for name, pattern in inline_patterns:
                match = pattern.search(remaining_text)
                if match and match.start() < earliest_pos:
                    earliest_match = match
                    earliest_pos = match.start()
                    pattern_name = name
            
            if earliest_match:
                # Add text before the match
                if earliest_pos > 0:
                    text_before = remaining_text[:earliest_pos]
                    if text_before:
                        content.append({"type": "text", "text": text_before})
                
                # Process the match
                matched_element = self._process_inline_match(pattern_name, earliest_match)
                if matched_element:
                    if isinstance(matched_element, list):
                        content.extend(matched_element)
                    else:
                        content.append(matched_element)
                
                # Continue with remaining text
                remaining_text = remaining_text[earliest_match.end():]
            else:
                # No more matches, add remaining text
                if remaining_text:
                    content.append({"type": "text", "text": remaining_text})
                break
        
        return content if content else [{"type": "text", "text": text}]
    
    def _process_inline_match(self, pattern_name: str, match: re.Match) -> Union[Dict[str, Any], List[Dict[str, Any]], None]:
        """Process a matched inline pattern."""
        try:
            if pattern_name == 'bold':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "strong"}]
                }
            
            elif pattern_name == 'italic':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "em"}]
                }
            
            elif pattern_name == 'underline':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "underline"}]
                }
            
            elif pattern_name == 'strikethrough':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "strike"}]
                }
            
            elif pattern_name == 'superscript':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "subsup", "attrs": {"type": "sup"}}]
                }
            
            elif pattern_name == 'subscript':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "subsup", "attrs": {"type": "sub"}}]
                }
            
            elif pattern_name == 'monospace':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "code"}]
                }
            
            elif pattern_name == 'citation':
                return {
                    "type": "text",
                    "text": match.group(1),
                    "marks": [{"type": "em"}]  # ADF doesn't have citation, use italic
                }
            
            elif pattern_name == 'color':
                color = match.group(1)
                text_content = match.group(2)
                
                # Validate color
                if not self._is_valid_color(color):
                    self._add_error(
                        ParseErrorType.INVALID_COLOR,
                        self.context.line_number,
                        0,
                        match.group(0),
                        f"Plain text: {text_content}",
                        f"Invalid color value: {color}"
                    )
                    return {"type": "text", "text": text_content}
                
                return {
                    "type": "text",
                    "text": text_content,
                    "marks": [{"type": "textColor", "attrs": {"color": color}}]
                }
            
            elif pattern_name == 'link_with_text':
                text = match.group(1)
                url = match.group(2)
                return {
                    "type": "text",
                    "text": text,
                    "marks": [{"type": "link", "attrs": {"href": url}}]
                }
            
            elif pattern_name == 'link_simple':
                url = match.group(1)
                return {
                    "type": "text",
                    "text": url,
                    "marks": [{"type": "link", "attrs": {"href": url}}]
                }
            
            elif pattern_name == 'image':
                src = match.group(1)
                return {
                    "type": "mediaSingle",
                    "content": [{
                        "type": "media",
                        "attrs": {
                            "type": "external",
                            "url": src,
                            "alt": src
                        }
                    }]
                }
            
            elif pattern_name == 'line_break':
                return {"type": "hardBreak"}
            
            elif pattern_name in ['code_block', 'noformat', 'quote']:
                # These should be handled at block level, but if found inline, treat as text
                return {"type": "text", "text": match.group(0)}
            
        except Exception as e:
            self._add_error(
                ParseErrorType.NESTED_FORMATTING,
                self.context.line_number,
                0,
                match.group(0),
                "Plain text",
                f"Inline formatting error: {e}"
            )
            return {"type": "text", "text": match.group(0)}
        
        return None
    
    def _is_valid_color(self, color: str) -> bool:
        """Validate color value."""
        # Hex colors
        if color.startswith('#'):
            return re.match(r'^#[a-fA-F0-9]{3}$|^#[a-fA-F0-9]{6}$', color) is not None
        
        # Named colors (basic set)
        named_colors = {
            'red', 'green', 'blue', 'yellow', 'orange', 'purple', 'pink',
            'brown', 'black', 'white', 'gray', 'grey', 'cyan', 'magenta'
        }
        return color.lower() in named_colors
    
    def _create_empty_paragraph(self) -> Dict[str, Any]:
        """Create an empty paragraph."""
        return {
            "type": "paragraph",
            "content": [{"type": "text", "text": ""}]
        }
    
    def _add_error(self, error_type: ParseErrorType, line_number: int, column: int, 
                   original_text: str, parsed_as: str, message: str):
        """Add a parsing error to the context."""
        error = ParseError(
            error_type=error_type,
            line_number=line_number,
            column=column,
            original_text=original_text,
            parsed_as=parsed_as,
            message=message
        )
        self.context.errors.append(error)
        
        if self.enable_logging:
            self.logger.warning(
                f"Parse error at line {line_number}: {message} "
                f"(Original: '{original_text}' -> Parsed as: '{parsed_as}')"
            )
    
    def _log_conversion_results(self, input_file: str, output_file: str):
        """Log the conversion results and errors."""
        self.logger.info(f"Conversion completed: {input_file} -> {output_file}")
        
        if self.context.errors:
            self.logger.warning(f"Encountered {len(self.context.errors)} parsing errors:")
            
            # Group errors by type
            errors_by_type = {}
            for error in self.context.errors:
                error_type = error.error_type.value
                if error_type not in errors_by_type:
                    errors_by_type[error_type] = []
                errors_by_type[error_type].append(error)
            
            # Print error summary
            print("\n" + "="*60)
            print("PARSING ERROR SUMMARY")
            print("="*60)
            
            for error_type, errors in errors_by_type.items():
                print(f"\n{error_type.upper()} ({len(errors)} occurrences):")
                print("-" * 40)
                
                for error in errors:
                    print(f"  Line {error.line_number}: {error.message}")
                    print(f"    Original: '{error.original_text}'")
                    print(f"    Parsed as: '{error.parsed_as}'")
                    print()
            
            print("="*60)
            print(f"Total errors: {len(self.context.errors)}")
            print("All errors have been handled gracefully and parsing continued.")
            print("="*60)
        else:
            print(f"\n✓ Conversion completed successfully with no errors!")
            print(f"  Input:  {input_file}")
            print(f"  Output: {output_file}")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get a summary of parsing errors."""
        errors_by_type = {}
        for error in self.context.errors:
            error_type = error.error_type.value
            if error_type not in errors_by_type:
                errors_by_type[error_type] = []
            errors_by_type[error_type].append({
                "line": error.line_number,
                "column": error.column,
                "original": error.original_text,
                "parsed_as": error.parsed_as,
                "message": error.message
            })
        
        return {
            "total_errors": len(self.context.errors),
            "errors_by_type": errors_by_type
        }


def main():
    """Command-line interface for the converter."""
    if len(sys.argv) != 2:
        print("Usage: python jira_wiki_to_adf.py <input_file.txt>")
        print("Output will be saved as <input_file>-adf.txt")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    try:
        converter = JiraWikiToADFConverter(enable_logging=True)
        output_file = converter.convert_file(input_file)
        
        # Print success message
        print(f"\n✓ Successfully converted Jira Wiki Markup to ADF!")
        print(f"  Input file:  {input_file}")
        print(f"  Output file: {output_file}")
        
        # Show error summary if there were any errors
        error_summary = converter.get_error_summary()
        if error_summary["total_errors"] > 0:
            print(f"\n⚠ Conversion completed with {error_summary['total_errors']} warnings/errors.")
            print("See the detailed error log above for more information.")
        
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during conversion: {e}")
        sys.exit(1)


# Example usage and testing functions
def create_test_file():
    """Create a test file with various Jira Wiki Markup elements for testing."""
    test_content = """h1. Main Document Title

This is a sample document with various Jira Wiki Markup elements.

h2. Text Formatting Examples

Here we have *bold text*, _italic text_, +underlined text+, -strikethrough text-, ^superscript^, and ~subscript~.

We also have {{monospace text}} and ??citation text??.

{color:red}This text is red{color} and {color:#0066cc}this text is blue{color}.

h2. Links and Images

Here's a [simple link|https://www.atlassian.com] and a [https://www.google.com].

Here's an image: !https://via.placeholder.com/150x100.png!

h2. Lists

Bullet list:
* First item
* Second item
** Nested item
** Another nested item
* Third item

Numbered list:
# First numbered item
# Second numbered item
## Nested numbered item
## Another nested numbered item
# Third numbered item

h2. Tables

||Header 1||Header 2||Header 3||
|Cell 1|Cell 2|Cell 3|
|Cell 4|Cell 5|Cell 6|

h2. Code Examples

Inline code: {{System.out.println("Hello World");}}

Code block with language:
{code:java}
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
{code}

Preformatted text:
{noformat}
This is preformatted text
    with preserved    spacing
        and indentation
{noformat}

h2. Quotes and Panels

{quote}
This is a quoted section.
It can span multiple lines and preserve formatting.
{quote}

{panel:title=Important Note}
This is a panel with a title.
It's useful for highlighting important information.
{panel}

{panel}
This is a panel without a title.
{panel}

h2. Other Elements

Horizontal rule:
----

Line break example:\\\\This text comes after a line break.

h3. Nested Formatting

This demonstrates *bold text with _italic inside_* and other combinations.

{color:green}Green text with *bold formatting*{color}

h3. Edge Cases

Empty lines should be handled properly.


Multiple empty lines above and below.


Tables with formatting:
||*Bold Header*||_Italic Header_||
|{{Code cell}}|{color:red}Red cell{color}|

h4. End of Document

This is the end of the test document.
"""
    
    with open('test_wiki_markup.txt', 'w', encoding='utf-8') as f:
        f.write(test_content)
    
    print("Created test file: test_wiki_markup.txt")
    return 'test_wiki_markup.txt'


def test_converter():
    """Test the converter with various examples."""
    print("Testing Jira Wiki Markup to ADF Converter")
    print("=" * 50)
    
    # Create test file
    test_file = create_test_file()
    
    # Convert the test file
    converter = JiraWikiToADFConverter(enable_logging=True)
    try:
        output_file = converter.convert_file(test_file)
        print(f"\nTest completed successfully!")
        print(f"Check the output file: {output_file}")
        
        # Show a preview of the ADF content
        with open(output_file, 'r', encoding='utf-8') as f:
            adf_content = json.load(f)
        
        print("\nADF Structure Preview:")
        print(f"- Document type: {adf_content.get('type')}")
        print(f"- Version: {adf_content.get('version')}")
        print(f"- Content blocks: {len(adf_content.get('content', []))}")
        
        # Show first few content blocks
        for i, block in enumerate(adf_content.get('content', [])[:3]):
            print(f"  Block {i+1}: {block.get('type')}")
            if block.get('attrs'):
                print(f"    Attributes: {block['attrs']}")
        
        if len(adf_content.get('content', [])) > 3:
            print(f"  ... and {len(adf_content['content']) - 3} more blocks")
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()


def validate_adf_structure(adf_content: Dict[str, Any]) -> bool:
    """Validate that the generated ADF has proper structure."""
    required_fields = ['type', 'version', 'content']
    
    for field in required_fields:
        if field not in adf_content:
            return False
    
    if adf_content['type'] != 'doc':
        return False
    
    if not isinstance(adf_content['content'], list):
        return False
    
    return True


if __name__ == "__main__":
    # Check if we're running tests
    if len(sys.argv) == 2 and sys.argv[1] == "--test":
        test_converter()
    else:
        main()

# TESTING
# Creates and converts a comprehensive test file#python jira_wiki_to_adf.py --test

#---------------------

# PROGRAMMATIC
# from jira_wiki_to_adf import JiraWikiToADFConverter

# converter = JiraWikiToADFConverter()
# output_file = converter.convert_file('input.txt')

# Or convert text directly
# adf_content = converter.convert_text(wiki_markup_text)

#---------------------

# python jira_wiki_to_adf.py input_file.txt
# Creates: input_file-adf.txt
