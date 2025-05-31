import re
import os

def find_reference_block(content: str) -> str | None:
    match = re.search(r"<details>\s*<summary><h2>Références</h2></summary>(.*?)<\/details>", content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip() # Keep strip here for overall block cleaning
    return None

def parse_reference_item(item_content: str) -> dict | None:
    data = {}
    # Corrected date regex: remove erroneous backslashes () which were in original prompt.
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", item_content) # Date should be YYYY-MM-DD
    if date_match:
        data['date'] = date_match.group(1)
        item_content = item_content.replace(date_match.group(1), "").strip() # Remove only date

    # Corrected link regex from original prompt for robustness with quotes:
    link_match = re.search(r"""<a\s+href=(?:'|")([^'"]*)(?:'|")>(.*?)</a>""", item_content, re.IGNORECASE)
    if not link_match:
        return None
    data['url'] = link_match.group(1)
    data['text'] = link_match.group(2).strip()
    item_content = item_content.replace(link_match.group(0), "").strip() # Remove the a tag
    item_content = re.sub(r'\s+', ' ', item_content).strip() # Normalize spaces

    known_types = [
        "ENTIEREMENT_MODIF", "MODIFIE", "APPLICATION", "CREATION",
        "ABROGE", "CITE", "ANNULE", "TRANSFERE", "RECTIFIE", "ABROGE_DIFF"
    ]
    found_type = "N/A" # Default
    parts = item_content.split(' ')
    # Filter out empty strings from parts that can result from multiple spaces
    parts = [p for p in parts if p]

    identified_types = [t for t in known_types if t in parts]

    if "ENTIEREMENT_MODIF" in identified_types and "MODIFIE" in identified_types:
        found_type = "ENTIEREMENT_MODIF"
    elif identified_types:
        identified_types.sort(key=len, reverse=True) # Prioritize longer specific types
        found_type = identified_types[0] # Takes the first one found based on sorted known_types order
    elif parts and parts[0].isupper() and len(parts[0]) > 1 and parts[0] not in ["HTML", "SOURCE", "CIBLE"]: # Check if first part looks like a type
             found_type = parts[0]

    data['type'] = found_type
    # data['text'] is already set from link_match.group(2)
    return data

def extract_references_from_html(html_content: str) -> tuple[list[dict], list[dict]]:
    incoming_refs = []
    outgoing_refs = []
    lines = html_content.splitlines() # Split content into lines
    current_section_title = None
    current_section_content_lines = []
    current_list_target = None

    for line_idx, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line.startswith("### "): # Potential section title
            # If there was a previous section with content and a valid target, process it
            if current_section_title and current_list_target is not None and current_section_content_lines:
                section_html = "\n".join(current_section_content_lines)
                # Search for the first UL block within this section's collected lines
                ul_match = re.search(r"<ul.*?>(.*?)</ul>", section_html, re.DOTALL | re.IGNORECASE)
                if ul_match:
                    items_html = re.findall(r"<li.*?>(.*?)</li>", ul_match.group(1), re.DOTALL | re.IGNORECASE)
                    for item_html in items_html:
                        parsed_item = parse_reference_item(item_html.strip())
                        if parsed_item:
                            current_list_target.append(parsed_item)

            # Start new section
            current_section_title = stripped_line
            current_section_content_lines = [] # Reset content lines for the new section
            section_title_lower = current_section_title.lower()

            if "faisant référence à l'article" in section_title_lower or                "textes faisant référence à l'article" in section_title_lower or                "articles faisant référence à l'article" in section_title_lower: # Catches variations
                current_list_target = incoming_refs
            elif "références faites par l'article" in section_title_lower:
                current_list_target = outgoing_refs
            else:
                current_list_target = None # Unknown section type
        # Only append lines if we are effectively "inside" a section that has started
        # AND that section is one we care about (current_list_target is not None)
        # Or if we haven't hit any "### " yet, just accumulate lines (might contain ULs not under a specific H3)
        elif current_section_title : # current_section_title implies we are past the first "###" or it's not relevant
            current_section_content_lines.append(line) # Append original line to preserve structure for regex

    # Process the very last section's content after the loop finishes
    if current_section_title and current_list_target is not None and current_section_content_lines:
        section_html = "\n".join(current_section_content_lines)
        ul_match = re.search(r"<ul.*?>(.*?)</ul>", section_html, re.DOTALL | re.IGNORECASE)
        if ul_match:
            items_html = re.findall(r"<li.*?>(.*?)</li>", ul_match.group(1), re.DOTALL | re.IGNORECASE)
            for item_html in items_html:
                parsed_item = parse_reference_item(item_html.strip())
                if parsed_item:
                    current_list_target.append(parsed_item)
    return incoming_refs, outgoing_refs

def generate_markdown_table(references: list[dict], title: str) -> str:
    if not references:
        return f"### {title}\n\nAucune référence de ce type.\n"

    has_date_column = any(ref.get('date') for ref in references)

    table_lines = []
    table_lines.append(f"### {title}")

    if has_date_column:
        table_lines.append("| Date       | Type    | Document                                    |")
        table_lines.append("| :--------- | :------ | :------------------------------------------ |")
    else:
        table_lines.append("| Type    | Document                                    |")
        table_lines.append("| :------ | :------------------------------------------ |")

    for ref in references:
        doc_link = f"[{ref['text']}]({ref['url']})"
        if has_date_column:
            table_lines.append(f"| {ref.get('date', '')} | {ref.get('type', 'N/A')} | {doc_link} |")
        else:
            table_lines.append(f"| {ref.get('type', 'N/A')} | {doc_link} |")

    return "\n".join(table_lines) + "\n"

def process_markdown_file(filepath: str):
    # print(f"Attempting to process file: {filepath}") # Included in __main__
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        # Return a status or raise exception for summary counting
        raise # Re-raise for the summary counter

    # Idempotency Check
    original_details_block_match_for_idempotency = re.search(r"<details>\s*<summary><h2>Références</h2></summary>(.*?)<\/details>", original_content, re.DOTALL | re.IGNORECASE)
    if original_details_block_match_for_idempotency:
        content_inside_details = original_details_block_match_for_idempotency.group(1)
        if ("### Textes citant cet article" in content_inside_details or             "### Cet article cite les textes suivants" in content_inside_details):
            print(f"Skipping {filepath} as it appears to be already processed.")
            return "skipped_idempotency" # Return status for summary
    # else: # No details block found at all, also a skip from processing perspective
        # print(f"No reference <details> block found in {filepath}. Skipping.")
        # return "skipped_no_details"


    original_details_block_match = re.search(r"<details>\s*<summary><h2>Références</h2></summary>.*?</details>", original_content, re.DOTALL | re.IGNORECASE)
    if not original_details_block_match:
        print(f"No reference <details> block found in {filepath} (overall match). Skipping.")
        return "skipped_no_details_block"

    original_details_block_outer_html = original_details_block_match.group(0)
    reference_html_content_inside_summary = find_reference_block(original_details_block_outer_html)

    if not reference_html_content_inside_summary:
        print(f"Reference block content (after summary) is empty in {filepath}. Skipping modification.")
        return "skipped_empty_refs"

    incoming_refs, outgoing_refs = extract_references_from_html(reference_html_content_inside_summary)

    if not incoming_refs and not outgoing_refs:
        print(f"No actual references parsed from {filepath} (HTML content: '{reference_html_content_inside_summary[:100]}...'). Skipping modification.")
        return "skipped_no_parsed_items"

    new_references_markdown_parts = []
    if incoming_refs:
        new_references_markdown_parts.append(generate_markdown_table(incoming_refs, "Textes citant cet article"))
    if outgoing_refs:
        new_references_markdown_parts.append(generate_markdown_table(outgoing_refs, "Cet article cite les textes suivants"))

    if not new_references_markdown_parts:
        print(f"Generated new reference content is empty for {filepath} (unexpected). Skipping modification.")
        return "skipped_empty_generation"

    new_references_markdown_combined = "\n\n".join(new_references_markdown_parts).strip()
    new_details_block_content = f"<details>\n  <summary><h2>Références</h2></summary>\n\n{new_references_markdown_combined}\n\n</details>"
    updated_content = original_content.replace(original_details_block_outer_html, new_details_block_content)

    if updated_content == original_content:
        print(f"No change made to {filepath} (content is identical after processing).")
        return "no_change"

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Successfully processed and updated {filepath}")
        return "processed" # Return status for summary
    except Exception as e:
        print(f"Error writing updated file {filepath}: {e}")
        raise # Re-raise for summary counter

if __name__ == "__main__":
    markdown_files = [
        "LICENCE.md", "README.md", "article_1.md", "article_preambule.md",
        "titre_ii/README.md", "titre_ii/article_10.md", "titre_ii/article_11.md", "titre_ii/article_12.md",
        "titre_ii/article_13.md", "titre_ii/article_14.md", "titre_ii/article_15.md", "titre_ii/article_16.md",
        "titre_ii/article_17.md", "titre_ii/article_18.md", "titre_ii/article_19.md", "titre_ii/article_5.md",
        "titre_ii/article_6.md", "titre_ii/article_7.md", "titre_ii/article_8.md", "titre_ii/article_9.md",
        "titre_iii/README.md", "titre_iii/article_20.md", "titre_iii/article_21.md", "titre_iii/article_22.md",
        "titre_iii/article_23.md",
        "titre_iv/README.md", "titre_iv/article_24.md", "titre_iv/article_25.md", "titre_iv/article_26.md",
        "titre_iv/article_27.md", "titre_iv/article_28.md", "titre_iv/article_29.md", "titre_iv/article_30.md",
        "titre_iv/article_31.md", "titre_iv/article_32.md", "titre_iv/article_33.md",
        "titre_ix/README.md", "titre_ix/article_67.md", "titre_ix/article_68.md",
        "titre_premier/README.md", "titre_premier/article_2.md", "titre_premier/article_3.md", "titre_premier/article_4.md",
        "titre_v/README.md", "titre_v/article_34-1.md", "titre_v/article_34.md", "titre_v/article_35.md",
        "titre_v/article_36.md", "titre_v/article_37-1.md", "titre_v/article_37.md", "titre_v/article_38.md",
        "titre_v/article_39.md", "titre_v/article_40.md", "titre_v/article_41.md", "titre_v/article_42.md",
        "titre_v/article_43.md", "titre_v/article_44.md", "titre_v/article_45.md", "titre_v/article_46.md",
        "titre_v/article_47-1.md", "titre_v/article_47-2.md", "titre_v/article_47.md", "titre_v/article_48.md",
        "titre_v/article_49.md", "titre_v/article_50-1.md", "titre_v/article_50.md", "titre_v/article_51-1.md",
        "titre_v/article_51-2.md", "titre_v/article_51.md",
        "titre_vi/README.md", "titre_vi/article_52.md", "titre_vi/article_53-1.md", "titre_vi/article_53-2.md",
        "titre_vi/article_53.md", "titre_vi/article_54.md", "titre_vi/article_55.md",
        "titre_vii/README.md", "titre_vii/article_56.md", "titre_vii/article_57.md", "titre_vii/article_58.md",
        "titre_vii/article_59.md", "titre_vii/article_60.md", "titre_vii/article_61-1.md", "titre_vii/article_61.md",
        "titre_vii/article_62.md", "titre_vii/article_63.md",
        "titre_viii/README.md", "titre_viii/article_64.md", "titre_viii/article_65.md", "titre_viii/article_66-1.md",
        "titre_viii/article_66.md",
        "titre_x/README.md", "titre_x/article_68-1.md", "titre_x/article_68-2.md", "titre_x/article_68-3.md",
        "titre_xi/README.md", "titre_xi/article_69.md", "titre_xi/article_70.md", "titre_xi/article_71.md",
        "titre_xi_bis/README.md", "titre_xi_bis/article_71-1.md",
        "titre_xii/README.md", "titre_xii/article_72-1.md", "titre_xii/article_72-2.md", "titre_xii/article_72-3.md",
        "titre_xii/article_72-4.md", "titre_xii/article_72.md", "titre_xii/article_73.md", "titre_xii/article_74-1.md",
        "titre_xii/article_74.md", "titre_xii/article_75-1.md", "titre_xii/article_75.md",
        "titre_xiii/README.md", "titre_xiii/article_76.md", "titre_xiii/article_77.md",
        "titre_xiv/README.md", "titre_xiv/article_87.md", "titre_xiv/article_88.md",
        "titre_xv/README.md", "titre_xv/article_88-1.md", "titre_xv/article_88-2.md", "titre_xv/article_88-3.md",
        "titre_xv/article_88-4.md", "titre_xv/article_88-5.md", "titre_xv/article_88-6.md", "titre_xv/article_88-7.md",
        "titre_xvi/README.md", "titre_xvi/article_89.md"
    ]

    results = {"processed": 0, "skipped_idempotency": 0, "skipped_no_details_block": 0,
               "skipped_empty_refs": 0, "skipped_no_parsed_items": 0,
               "skipped_empty_generation":0, "no_change": 0, "error": 0, "file_not_found": 0}

    for md_file in markdown_files:
        print(f"--- Processing: {md_file} ---")
        if os.path.exists(md_file):
            try:
                status = process_markdown_file(md_file)
                if status in results:
                    results[status] += 1
                else: # Should not happen if process_markdown_file returns defined statuses
                    results["error"] += 1
            except Exception as e: # Catch errors from process_markdown_file (like read/write)
                print(f"Critical error during processing of {md_file}: {e}")
                results["error"] += 1
        else:
            print(f"File not found: {md_file}")
            results["file_not_found"] += 1

    print(f"\n--- Summary ---")
    print(f"Successfully updated files: {results['processed']}")
    print(f"Skipped (already processed by idempotency): {results['skipped_idempotency']}")
    print(f"Skipped (no <details> block found): {results['skipped_no_details_block']}")
    print(f"Skipped (empty content in <details> block): {results['skipped_empty_refs']}")
    print(f"Skipped (no items parsed from HTML): {results['skipped_no_parsed_items']}")
    print(f"Skipped (no new content generated): {results['skipped_empty_generation']}")
    print(f"Skipped (no change needed to file): {results['no_change']}")
    print(f"Files not found: {results['file_not_found']}")
    print(f"Errors during processing: {results['error']}")
    print("Full script execution complete. Review logs for details on processed files.")
