import re
import json
import sys

class JiraWikiToADF:
    def __init__(self):
        self.errors = []  # Collect format errors

    def log_error(self, msg):
        self.errors.append(msg)

    def parse_file(self, input_path, output_path):
        # Read all lines
        with open(input_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Initialize ADF document
        adf = {"version": 1, "type": "doc", "content": []}
        i = 0
        while i < len(lines):
            line = lines[i].rstrip('\n')
            # Check for code block
            if line.startswith("{code"):
                block_node, skip_to = self.parse_code_block(lines, i)
                adf["content"].append(block_node)
                i = skip_to
                continue

            # Check for noformat block
            if line.strip() == "{noformat}":
                block_node, skip_to = self.parse_noformat_block(lines, i)
                adf["content"].append(block_node)
                i = skip_to
                continue

            # Check for panel block
            if line.startswith("{panel"):
                block_node, skip_to = self.parse_panel_block(lines, i)
                adf["content"].append(block_node)
                i = skip_to
                continue

            # Headings
            m = re.match(r"^h([1-6])\.\s+(.*)", line)
            if m:
                level = int(m.group(1))
                text = m.group(2)
                heading_node = {
                    "type": "heading", 
                    "attrs": {"level": level},
                    "content": self.parse_inline(text)
                }
                adf["content"].append(heading_node)
                i += 1
                continue

            # Horizontal rule
            if line.strip() == "----":
                adf["content"].append({"type": "rule"})
                i += 1
                continue

            # Lists
            if re.match(r"^(\*|-|\#)+\s+", line):
                list_node, skip_to = self.parse_list(lines, i)
                adf["content"].append(list_node)
                i = skip_to
                continue

            # Table
            if line.startswith("||") or line.startswith("|"):
                table_node, skip_to = self.parse_table(lines, i)
                adf["content"].append(table_node)
                i = skip_to
                continue

            # Blockquote (single line)
            if line.startswith("bq. "):
                quote_text = line[4:]
                quote_node = {"type": "blockquote", "content": [
                    {"type": "paragraph", "content": self.parse_inline(quote_text)}
                ]}
                adf["content"].append(quote_node)
                i += 1
                continue

            # Blank line = new paragraph boundary
            if line.strip() == "":
                i += 1
                continue

            # Otherwise treat as a paragraph (possibly spanning multiple lines)
            para_lines = [line]
            i += 1
            # Gather following non-blank lines as one paragraph
            while i < len(lines) and lines[i].strip() != "" and not re.match(r"^(h[1-6]\.|----|\* |\# |bq\. |\{|\|)", lines[i]):
                para_lines.append(lines[i].rstrip('\n'))
                i += 1
            paragraph_text = " ".join(para_lines).strip()
            para_node = {"type": "paragraph", "content": self.parse_inline(paragraph_text)}
            adf["content"].append(para_node)

        # Write output ADF JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(adf, f, indent=2)

        # Write error log
        log_path = output_path.replace(".txt", "-errors.log")
        with open(log_path, 'w', encoding='utf-8') as logf:
            for err in self.errors:
                logf.write(err + "\n")

    def parse_inline(self, text):
        """
        Parse inline markup within a single line of text.
        Returns a list of ADF inline nodes (text with marks, mentions, links, etc.).
        """
        # This is a simplified example. A full implementation would handle nested and multiple marks.
        nodes = []
        # Handle mention [~user]
        text = re.sub(r"\[~([^\]]+)\]", 
                      lambda m: self.convert_mention(m.group(1)),
                      text)
        # Handle links [text|url] or [url]
        def link_repl(m):
            label = m.group(1) or m.group(2)
            url = m.group(2) or m.group(1)
            text_node = {"type": "text", "text": label}
            link_mark = {"type": "link", "attrs": {"href": url, "title": label}}
            text_node["marks"] = [link_mark]
            return json.dumps(text_node)  # temporary replacement marker
        text = re.sub(r"\[([^|\]]+)\|([^]]+)\]|\[([hH][tT][tT][pP][^\]]+)\]", 
                      link_repl, text)
        # Escape any inserted JSON from link_repl
        parts = text.split('"type":')
        for part in parts:
            if part.strip().startswith("text"):
                # A JSON blob inserted
                try:
                    node = json.loads("{" + part)
                    nodes.append(node)
                    continue
                except json.JSONDecodeError:
                    pass
        # After extracting links, remove placeholders
        # For simplicity, assume no leftover
        # Handle bold, italics, etc. (one pass example, not nested):
        def style_repl(type_name, mark_type):
            return lambda m: self.wrap_mark(m, mark_type)
        # Bold
        text = re.sub(r"\*(.*?)\*", style_repl("text", "strong"), text)
        # Italic
        text = re.sub(r"_(.*?)_", style_repl("text", "em"), text)
        # Strike
        text = re.sub(r"-(.*?)-", style_repl("text", "strike"), text)
        # Inline code
        text = re.sub(r"\{\{(.*?)\}\}", lambda m: self.wrap_mark(m, "code"), text)

        # Split remaining text by markers we handled (we used JSON injections above)
        # For simplicity, any leftover text is plain
        if text:
            nodes.append({"type": "text", "text": text})
        return nodes

    def wrap_mark(self, match, mark_type):
        """
        Wrap the matched group in a JSON text node with the given mark.
        Used in regex replacement: returns a JSON string.
        """
        inner_text = match.group(1)
        text_node = {"type": "text", "text": inner_text, 
                     "marks": [{"type": mark_type}]}
        return json.dumps(text_node)

    def convert_mention(self, username):
        """
        Convert [~username] to an ADF mention node JSON string.
        Here we put username as text; ID is unknown.
        """
        mention_node = {
            "type": "mention",
            "attrs": {
                # In real use, look up the user's Atlassian account ID; here we leave empty or username
                "id": "",  
                "text": "@" + username
            }
        }
        return json.dumps(mention_node)

    def parse_code_block(self, lines, start_idx):
        """
        Handles lines from {code} to {code}. Returns a codeBlock node and the index after the block.
        """
        first_line = lines[start_idx].strip()
        # Extract language if given: {code:lang} or {code:title=...|borderStyle...}
        lang_match = re.match(r"\{code:([^}|]+)", first_line)
        language = lang_match.group(1) if lang_match else None
        content_lines = []
        i = start_idx + 1
        while i < len(lines):
            if lines[i].strip().startswith("{code}"):
                break
            content_lines.append(lines[i].rstrip('\n'))
            i += 1
        if i >= len(lines):
            self.log_error(f"Line {start_idx+1}: Unclosed {{code}} block; closing at EOF")
        code_text = "\n".join(content_lines)
        code_node = {"type": "codeBlock", 
                     "attrs": {"language": language} if language else {},
                     "content": [{"type": "text", "text": code_text}]}
        return code_node, i+1

    def parse_noformat_block(self, lines, start_idx):
        """
        Handles {noformat} ... {noformat} blocks, similar to code but no syntax highlighting.
        """
        i = start_idx + 1
        content_lines = []
        while i < len(lines):
            if lines[i].strip() == "{noformat}":
                break
            content_lines.append(lines[i].rstrip('\n'))
            i += 1
        if i >= len(lines):
            self.log_error(f"Line {start_idx+1}: Unclosed {{noformat}} block; closing at EOF")
        text = "\n".join(content_lines)
        block = {"type": "codeBlock", "content": [{"type": "text", "text": text}]}
        return block, i+1

    def parse_panel_block(self, lines, start_idx):
        """
        Handles {panel} ... {panel} blocks. Converts to ADF panel node.
        """
        first_line = lines[start_idx].strip()
        # Check for title or type parameter
        title_match = re.search(r"title=([^|}]+)", first_line)
        panel_type = "info"  # default if no explicit type
        if title_match:
            panel_title = title_match.group(1)
        else:
            panel_title = None
        content_lines = []
        i = start_idx + 1
        while i < len(lines):
            if lines[i].strip().startswith("{panel}"):
                break
            content_lines.append(lines[i].rstrip('\n'))
            i += 1
        if i >= len(lines):
            self.log_error(f"Line {start_idx+1}: Unclosed {{panel}} block; closing at EOF")
        # Create panel node with one paragraph child per line
        panel_node = {"type": "panel", "attrs": {"panelType": panel_type}, "content": []}
        for para in content_lines:
            para_node = {"type": "paragraph", "content": self.parse_inline(para)}
            panel_node["content"].append(para_node)
        # If there was a title, we could insert it as first paragraph or as an attribute; simplified here:
        if panel_title:
            panel_node["content"].insert(0, 
                {"type":"paragraph", "content":[{"type":"text","text":panel_title}]})
        return panel_node, i+1

    def parse_list(self, lines, start_idx):
        """
        Handles both bulleted and numbered lists. Returns a list node and next index.
        """
        items = []
        list_type = None
        i = start_idx
        while i < len(lines):
            line = lines[i]
            m = re.match(r"^(\*|\-|\#)+\s+(.*)", line)
            if not m:
                break
            marker = m.group(1)
            text = m.group(2)
            # Determine list type by first character
            if marker[0] == "#":
                list_type = "orderedList"
            else:
                list_type = "bulletList"
            item_node = {"type": "listItem", 
                         "content": [{"type": "paragraph", "content": self.parse_inline(text)}]}
            items.append(item_node)
            i += 1
        if not list_type:
            # Should not happen
            self.log_error(f"Line {start_idx+1}: List parsing error")
            return {}, i
        list_node = {"type": list_type, "content": items}
        return list_node, i

    def parse_table(self, lines, start_idx):
        """
        Parses a simple table. Assumes well-formed header and row lines.
        """
        rows = []
        i = start_idx
        while i < len(lines):
            line = lines[i].rstrip('\n')
            if not (line.startswith("||") or line.startswith("|")):
                break
            cells = [cell for cell in re.split(r"\|", line) if cell != ""]
            if line.startswith("||"):
                # Header row
                row = {"type": "tableHeader", "content": []}
            else:
                row = {"type": "tableRow", "content": []}
            for cell_text in cells:
                # Skip the first empty split if line started with |
                if cell_text.strip() == "":
                    continue
                cell_node = {"type": "tableCell", "content": [
                    {"type": "paragraph", "content": self.parse_inline(cell_text.strip())}
                ]}
                row["content"].append(cell_node)
            rows.append(row)
            i += 1
        if not rows:
            self.log_error(f"Line {start_idx+1}: Table parsing found no rows.")
        table_node = {"type": "table", "content": rows}
        return table_node, i

if __name__ == "__main__":
    parser = JiraWikiToADF()
    parser.parse_file(sys.argv[1], sys.argv[2])


# Example usage:
# python3 wiki2adf.py input-1.txt output-1.txt