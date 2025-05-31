import re
import os

# Version from new plan step 1 (extracts 'sens')
def parse_reference_item(item_content: str) -> dict | None:
    data = {}
    # Corrected date regex (remove '' and ensure group(1) is used for replacement)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", item_content)
    if date_match:
        data['date'] = date_match.group(1)
        # Replace only the matched date string
        item_content = item_content.replace(date_match.group(1), "").strip()

    link_match = re.search(r"""<a\s+href=(?:'|")([^'"]*)(?:'|")>(.*?)</a>""", item_content, re.IGNORECASE) # Corrected quotes
    if not link_match:
        return None
    data['url'] = link_match.group(1)
    data['text'] = link_match.group(2).strip()

    item_content_after_link = item_content.replace(link_match.group(0), "")
    item_content_normalized = re.sub(r'\s+', ' ', item_content_after_link).strip()
    parts = [p for p in item_content_normalized.split(' ') if p]

    known_types = [
        "ENTIEREMENT_MODIF", "MODIFIE", "APPLICATION", "CREATION",
        "ABROGE", "CITE", "ANNULE", "TRANSFERE", "RECTIFIE", "ABROGE_DIFF"
    ]
    found_type = "N/A"
    remaining_parts_for_sens = list(parts) # Operate on a copy for sens extraction

    # Type extraction logic
    # Prioritize more specific types if they are composed of shorter known types
    identified_types_in_parts = [t for t in known_types if t in parts]
    if "ENTIEREMENT_MODIF" in identified_types_in_parts and "MODIFIE" in identified_types_in_parts:
        found_type = "ENTIEREMENT_MODIF"
        # Remove both parts for sens extraction if ENTIEREMENT_MODIF is chosen
        if "ENTIEREMENT_MODIF" in remaining_parts_for_sens: remaining_parts_for_sens.remove("ENTIEREMENT_MODIF")
        if "MODIFIE" in remaining_parts_for_sens: remaining_parts_for_sens.remove("MODIFIE")
    elif identified_types_in_parts:
        identified_types_in_parts.sort(key=len, reverse=True) # Sort by length to get most specific
        found_type = identified_types_in_parts[0]
        if found_type in remaining_parts_for_sens: remaining_parts_for_sens.remove(found_type) # Remove the found type
    elif parts and parts[0] and parts[0].isupper() and len(parts[0]) > 1 and parts[0] not in ["HTML", "SOURCE", "CIBLE"]: # Check parts[0] is not empty and avoid common non-type words
        found_type = parts[0]
        if found_type in remaining_parts_for_sens: remaining_parts_for_sens.remove(found_type)

    data['type'] = found_type

    # Sens extraction from remaining_parts_for_sens
    found_sens = "N/A" # Default if not found
    temp_remaining_after_sens = []
    sens_found_this_iteration = False
    for part_val in remaining_parts_for_sens:
        if not sens_found_this_iteration:
            if part_val.lower() == "source":
                found_sens = "source"
                sens_found_this_iteration = True
                continue
            elif part_val.lower() == "cible":
                found_sens = "cible"
                sens_found_this_iteration = True
                continue
        temp_remaining_after_sens.append(part_val)

    # Note: remaining_parts_for_sens might still contain other descriptive words.
    # The current logic for 'sens' only extracts 'source' or 'cible'.
    # data['text'] is from inside the link, so it's not touched by this.
    data['sens'] = found_sens
    return data

# Version from new plan step 2 (adds 'Sens' column)
def generate_markdown_table(references: list[dict], title: str) -> str:
    if not references:
        return f"### {title}\n\nAucune référence de ce type.\n"
    has_date_column = any(ref.get('date') for ref in references)
    table_lines = []
    table_lines.append(f"### {title}")
    if has_date_column:
        table_lines.append("| Date       | Type    | Sens    | Document                                    |")
        table_lines.append("| :--------- | :------ | :------ | :------------------------------------------ |")
    else:
        table_lines.append("| Type    | Sens    | Document                                    |")
        table_lines.append("| :------ | :------ | :------------------------------------------ |")
    for ref in references:
        doc_link = f"[{ref['text']}]({ref['url']})"
        sens_value = ref.get('sens', 'N/A') # Default to N/A if 'sens' is not present
        if has_date_column:
            table_lines.append(f"| {ref.get('date', '')} | {ref.get('type', 'N/A')} | {sens_value} | {doc_link} |")
        else:
            table_lines.append(f"| {ref.get('type', 'N/A')} | {sens_value} | {doc_link} |")
    return "\n".join(table_lines) + "\n" # Ensure final newline for separation

# Helper functions (find_reference_block, extract_references_from_html) are from the last fully working script
def find_reference_block(content: str) -> str | None:
    match = re.search(r"<details>\s*<summary><h2>Références</h2></summary>(.*?)<\/details>", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def extract_references_from_html(html_content: str) -> tuple[list[dict], list[dict]]:
    incoming_refs = []
    outgoing_refs = []
    lines = html_content.splitlines()
    current_section_title = None
    current_section_content_lines = []
    current_list_target = None
    for line_idx, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line.startswith("### "):
            if current_section_title and current_list_target is not None and current_section_content_lines: # Process previous section if valid
                section_html = "\n".join(current_section_content_lines)
                ul_match = re.search(r"<ul.*?>(.*?)</ul>", section_html, re.DOTALL | re.IGNORECASE)
                if ul_match:
                    items_html = re.findall(r"<li.*?>(.*?)</li>", ul_match.group(1), re.DOTALL | re.IGNORECASE)
                    for item_html in items_html:
                        parsed_item = parse_reference_item(item_html.strip()) # Uses the new parse_reference_item
                        if parsed_item:
                            current_list_target.append(parsed_item)
            current_section_title = stripped_line
            current_section_content_lines = []
            section_title_lower = current_section_title.lower()
            if "faisant référence à l'article" in section_title_lower or                "textes faisant référence à l'article" in section_title_lower or                "articles faisant référence à l'article" in section_title_lower:
                current_list_target = incoming_refs
            elif "références faites par l'article" in section_title_lower:
                current_list_target = outgoing_refs
            else: current_list_target = None
        elif current_section_title : # only append if current_section_title is set (i.e. we are past the first relevant ###)
             if current_list_target is not None: # only append if the current section is one we care about
                current_section_content_lines.append(line)
             elif not current_section_content_lines: # If target is None, but we just started, keep the line if it's part of a list not under a header we want
                  if stripped_line.startswith("<ul") or stripped_line.startswith("<li"):
                       current_section_content_lines.append(line)


    if current_section_title and current_list_target is not None and current_section_content_lines: # Process last section
        section_html = "\n".join(current_section_content_lines)
        ul_match = re.search(r"<ul.*?>(.*?)</ul>", section_html, re.DOTALL | re.IGNORECASE)
        if ul_match:
            items_html = re.findall(r"<li.*?>(.*?)</li>", ul_match.group(1), re.DOTALL | re.IGNORECASE)
            for item_html in items_html:
                parsed_item = parse_reference_item(item_html.strip())
                if parsed_item: current_list_target.append(parsed_item)
    return incoming_refs, outgoing_refs

# Main processing function with adjusted idempotency for this re-processing task
def process_markdown_file(filepath: str):
    print(f"Attempting to process file: {filepath}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return

    # Idempotency Check: Skip if the NEW table format (with 'Sens') is already present.
    new_format_fully_present = False
    original_details_block_match_for_idempotency = re.search(r"<details>\s*<summary><h2>Références</h2></summary>(.*?)<\/details>", original_content, re.DOTALL | re.IGNORECASE)
    if original_details_block_match_for_idempotency:
        content_inside_details = original_details_block_match_for_idempotency.group(1)
        if ("| Type    | Sens    | Document" in content_inside_details or             "| Date       | Type    | Sens    | Document" in content_inside_details) and            ("### Textes citant cet article" in content_inside_details or             "### Cet article cite les textes suivants" in content_inside_details):
            new_format_fully_present = True

    if new_format_fully_present:
        print(f"Skipping {filepath} as it already contains Markdown tables with 'Sens' column.")
        return

    # Proceed to find and replace the original HTML block if not skipped
    original_details_block_match = re.search(r"<details>\s*<summary><h2>Références</h2></summary>.*?</details>", original_content, re.DOTALL | re.IGNORECASE)
    if not original_details_block_match:
        print(f"No reference <details> block found in {filepath}. Skipping.") # No block to process
        return

    original_details_block_outer_html = original_details_block_match.group(0)
    reference_html_content_inside_summary = find_reference_block(original_details_block_outer_html)

    # If reference_html_content_inside_summary is None or empty, it means the block was there but empty,
    # or find_reference_block failed (e.g. if it was an old table format without <ul>).
    # We should try to parse it; if it's empty or unparsable, empty ref lists will be returned.

    incoming_refs, outgoing_refs = extract_references_from_html(reference_html_content_inside_summary if reference_html_content_inside_summary else "")

    # Ensure sections are created even if they are empty, if the original HTML had those section titles.
    # This handles cases where an old table might be cleared out, or an empty HTML list section needs a table.
    create_incoming_section = "faisant référence à l'article" in reference_html_content_inside_summary.lower() if reference_html_content_inside_summary else False
    create_outgoing_section = "références faites par l'article" in reference_html_content_inside_summary.lower() if reference_html_content_inside_summary else False

    if not incoming_refs and not outgoing_refs and not create_incoming_section and not create_outgoing_section:
        if reference_html_content_inside_summary: # Only print if there was non-empty content that yielded nothing
             print(f"No actual references parsed from HTML content in {filepath} and no recognized section titles found. Block will be replaced.")
        # If block was empty and no titles, effectively it's an empty references section.
        # Let it proceed to generate empty tables under standard titles if no specific titles were in original HTML.
        # To avoid empty <details> if no titles at all, this will make it generate "Aucune reference" for both.
        create_incoming_section = True
        create_outgoing_section = True


    new_references_markdown_parts = []
    if incoming_refs or create_incoming_section:
        new_references_markdown_parts.append(generate_markdown_table(incoming_refs, "Textes citant cet article"))

    if outgoing_refs or create_outgoing_section:
        new_references_markdown_parts.append(generate_markdown_table(outgoing_refs, "Cet article cite les textes suivants"))

    if not new_references_markdown_parts:
        # This case should ideally not be reached if we default to creating sections.
        # But as a fallback, replace with an empty reference section.
        print(f"No reference sections to generate for {filepath}. Replacing matched <details> block with empty.")
        new_references_markdown_combined = "Auncune référence trouvée." # Placeholder if needed
    else:
        new_references_markdown_combined = "\n\n".join(new_references_markdown_parts).strip()

    new_details_block_content = f"<details>\n  <summary><h2>Références</h2></summary>\n\n{new_references_markdown_combined}\n\n</details>"
    updated_content = original_content.replace(original_details_block_outer_html, new_details_block_content)

    if updated_content == original_content:
        print(f"No change made to {filepath} (content is identical after processing or block was not targeted).")
        return

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Successfully processed and updated {filepath} with 'Sens' column.")
    except Exception as e:
        print(f"Error writing updated file {filepath}: {e}")

if __name__ == "__main__":
    files_to_process = ["article_1.md", "titre_ii/article_10.md"]

    print("IMPORTANT: Ensure article_1.md and titre_ii/article_10.md are reverted to original HTML list format before this script runs.")

    for f_path in files_to_process:
        if os.path.exists(f_path):
            process_markdown_file(f_path)
        else:
            print(f"Test file not found: {f_path}")

    print("Script execution complete. Check modified sample files for the 'Sens' column and its correctness.")
