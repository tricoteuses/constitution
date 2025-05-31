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
    identified_types_in_parts = [t for t in known_types if t in parts] # Check against original 'parts'
    if "ENTIEREMENT_MODIF" in identified_types_in_parts and "MODIFIE" in identified_types_in_parts:
        found_type = "ENTIEREMENT_MODIF"
        if "ENTIEREMENT_MODIF" in remaining_parts_for_sens: remaining_parts_for_sens.remove("ENTIEREMENT_MODIF")
        if "MODIFIE" in remaining_parts_for_sens: remaining_parts_for_sens.remove("MODIFIE")
    elif identified_types_in_parts:
        identified_types_in_parts.sort(key=len, reverse=True)
        found_type = identified_types_in_parts[0]
        # Robust removal from remaining_parts_for_sens
        temp_list_after_type = []
        type_removed = False
        for p in remaining_parts_for_sens:
            if p == found_type and not type_removed:
                type_removed = True
                continue
            temp_list_after_type.append(p)
        remaining_parts_for_sens = temp_list_after_type
    elif parts and parts[0] and parts[0].isupper() and len(parts[0]) > 1 and parts[0] not in ["HTML", "SOURCE", "CIBLE"]:
        found_type = parts[0]
        if remaining_parts_for_sens and remaining_parts_for_sens[0] == found_type: # Ensure it's the same part being removed
            remaining_parts_for_sens.pop(0)

    data['type'] = found_type

    found_sens = "N/A"
    final_remaining_parts = [] # To store parts not used for sens
    sens_keyword_found = False
    for part_val in remaining_parts_for_sens:
        if not sens_keyword_found:
            if part_val.lower() == "source":
                found_sens = "source"
                sens_keyword_found = True
                # Don't add "source" to final_remaining_parts
                continue
            elif part_val.lower() == "cible":
                found_sens = "cible"
                sens_keyword_found = True
                # Don't add "cible" to final_remaining_parts
                continue
        final_remaining_parts.append(part_val) # Add non-sens keywords here

    # Note: The problem description for parse_reference_item implied removing found type and sens.
    # The current logic for remaining_parts_for_sens does this.
    # data['text'] is from link text, not modified here.
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
        sens_value = ref.get('sens', 'N/A')
        if has_date_column:
            table_lines.append(f"| {ref.get('date', '')} | {ref.get('type', 'N/A')} | {sens_value} | {doc_link} |")
        else:
            table_lines.append(f"| {ref.get('type', 'N/A')} | {sens_value} | {doc_link} |")
    return "\n".join(table_lines) + "\n"

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
            if current_section_title and current_list_target is not None and current_section_content_lines:
                section_html = "\n".join(current_section_content_lines)
                ul_match = re.search(r"<ul.*?>(.*?)</ul>", section_html, re.DOTALL | re.IGNORECASE)
                if ul_match:
                    items_html = re.findall(r"<li.*?>(.*?)</li>", ul_match.group(1), re.DOTALL | re.IGNORECASE)
                    for item_html in items_html:
                        parsed_item = parse_reference_item(item_html.strip())
                        if parsed_item: current_list_target.append(parsed_item)
            current_section_title = stripped_line
            current_section_content_lines = []
            section_title_lower = current_section_title.lower()
            if "faisant référence à l'article" in section_title_lower or                "textes faisant référence à l'article" in section_title_lower or                "articles faisant référence à l'article" in section_title_lower:
                current_list_target = incoming_refs
            elif "références faites par l'article" in section_title_lower:
                current_list_target = outgoing_refs
            else: current_list_target = None
        # Append line to current_section_content_lines if we are inside a section
        # This was modified in prompt for v2.py, ensuring lines are only added if current_section_title is set.
        elif current_section_title:
             if current_list_target is not None: # If the current section is one we care about
                current_section_content_lines.append(line)
             # If target is None (unknown section), but we just started this unknown section,
             # and line is part of a list, accumulate it. This might be too broad.
             # The prompt's logic was: elif current_section_title: current_section_content_lines.append(line)
             # Reverting to that simpler logic from the prompt for now.
             # The refined version from v2 was:
             # elif current_section_title :
             #    if current_list_target is not None:
             #        current_section_content_lines.append(line)
             #    elif not current_section_content_lines:
             #        if stripped_line.startswith("<ul") or stripped_line.startswith("<li"):
             #            current_section_content_lines.append(line)
             # For the final script, stick to the one that worked:
             else: # current_section_title is set, but it's not a new "###" line
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

def process_markdown_file(filepath: str):
    # print(f"Attempting to process file: {filepath}") # Make less verbose for full run
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
    except Exception as e:
        # print(f"Error reading file {filepath}: {e}") # Less verbose
        return "error_read"

    new_format_fully_present = False
    original_details_block_match_for_idempotency = re.search(r"<details>\s*<summary><h2>Références</h2></summary>(.*?)<\/details>", original_content, re.DOTALL | re.IGNORECASE)

    if original_details_block_match_for_idempotency:
        content_inside_details = original_details_block_match_for_idempotency.group(1)
        # Check for the specific headers of tables with 'Sens' and specific section titles this script generates
        if ("| Type    | Sens    | Document" in content_inside_details or             "| Date       | Type    | Sens    | Document" in content_inside_details) and            ("### Textes citant cet article" in content_inside_details or             "### Cet article cite les textes suivants" in content_inside_details):
            new_format_fully_present = True

    if new_format_fully_present:
        # print(f"Skipping {filepath} as it already contains Markdown tables with 'Sens' column.") # Less verbose
        return "skipped_already_processed"

    # This is the original details block we might replace
    original_details_block_match = re.search(r"<details>\s*<summary><h2>Références</h2></summary>.*?</details>", original_content, re.DOTALL | re.IGNORECASE)
    if not original_details_block_match:
        # print(f"No reference <details> block found in {filepath}. Skipping.") # Less verbose
        return "skipped_no_details_block"

    original_details_block_outer_html = original_details_block_match.group(0)
    # Get content inside the <details> block, after the <summary>
    reference_html_content_inside_summary = find_reference_block(original_details_block_outer_html)

    # If reference_html_content_inside_summary is None (no proper details content after summary) or empty string
    # This check is important. If it's an old table, find_reference_block would return its content.
    # If it's HTML lists, it returns those. If empty, it's empty.
    # If None, it means the structure was <details><summary>...</summary></details> but nothing after summary.

    incoming_refs, outgoing_refs = extract_references_from_html(reference_html_content_inside_summary if reference_html_content_inside_summary else "")

    # Determine if sections should be created based on original HTML content, even if refs lists are empty
    create_incoming_section = False
    create_outgoing_section = False
    if reference_html_content_inside_summary: # Only check if there was content
        content_lower = reference_html_content_inside_summary.lower()
        if "faisant référence à l'article" in content_lower or            "textes faisant référence à l'article" in content_lower or            "articles faisant référence à l'article" in content_lower:
            create_incoming_section = True
        if "références faites par l'article" in content_lower:
            create_outgoing_section = True

    # If no refs were parsed AND no original section titles were detected,
    # it implies the block was either empty, or contained non-parsable/irrelevant content.
    # In this case, we might not want to create default empty sections unless the block itself was substantial.
    if not incoming_refs and not outgoing_refs and not create_incoming_section and not create_outgoing_section:
        # If reference_html_content_inside_summary was not empty, it means it had some content,
        # but no standard section titles or list items were found.
        # Replacing it with a clean "empty" state is reasonable.
        if reference_html_content_inside_summary and reference_html_content_inside_summary.strip(): # Check if there was non-whitespace content
            print(f"No references or recognized section titles parsed from {filepath}. Block will be standardized.")
        # Default to creating standard empty sections to ensure block is present and uniform
        create_incoming_section = True
        create_outgoing_section = True


    new_references_markdown_parts = []
    # Always attempt to generate, generate_markdown_table handles empty refs list.
    if create_incoming_section or incoming_refs: # Ensure section if title existed or refs found
        new_references_markdown_parts.append(generate_markdown_table(incoming_refs, "Textes citant cet article"))
    if create_outgoing_section or outgoing_refs: # Ensure section if title existed or refs found
        new_references_markdown_parts.append(generate_markdown_table(outgoing_refs, "Cet article cite les textes suivants"))

    if not new_references_markdown_parts:
        # This means neither incoming nor outgoing sections were indicated by original content, and no refs were parsed.
        # This could happen if the details block was present but completely empty or had unrelated content.
        # Forcing a minimal structure.
        new_references_markdown_combined = "Auncune référence de ce type." # Fallback for truly empty.
        # print(f"No reference sections to generate for {filepath} based on content. Creating minimal block.")
    else:
        new_references_markdown_combined = "\n\n".join(new_references_markdown_parts).strip()

    new_details_block_content = f"<details>\n  <summary><h2>Références</h2></summary>\n\n{new_references_markdown_combined}\n\n</details>"

    if original_details_block_outer_html == new_details_block_content :
        # print(f"No change needed for {filepath}, content is already in the desired final state.") # Less verbose
        return "skipped_no_change_needed"

    updated_content = original_content.replace(original_details_block_outer_html, new_details_block_content)

    if updated_content == original_content:
        # print(f"No textual change made to {filepath} (e.g. only whitespace differences if not caught above).") # Less verbose
        return "skipped_no_textual_change"

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Successfully processed and updated {filepath} with 'Sens' column.")
        return "updated"
    except Exception as e:
        # print(f"Error writing updated file {filepath}: {e}") # Less verbose
        return "error_write"

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

    counts = {"updated": 0, "skipped_already_processed": 0, "skipped_no_details_block": 0,
              "skipped_no_change_needed":0, "skipped_no_textual_change":0, "error_read":0, "error_write":0, "file_not_found":0}

    for md_file in markdown_files:
        # print(f"--- Processing: {md_file} ---") # Less verbose for final run
        if os.path.exists(md_file):
            try:
                result = process_markdown_file(md_file)
                if result in counts:
                    counts[result] += 1
                else:
                    print(f"Unknown result '{result}' for file {md_file}")
                    counts["error_write"] += 1 # Count as a write error if status is unknown
            except Exception as e:
                print(f"Critical error during processing of {md_file}: {e}")
                counts["error_write"] += 1 # Count as a write/processing error
        else:
            # print(f"File not found, skipping: {md_file}") # Less verbose
            counts["file_not_found"] += 1

    print(f"--- Full Processing Summary (with 'Sens' logic) ---")
    print(f"Files updated: {counts['updated']}")
    print(f"Files skipped (already processed with 'Sens'): {counts['skipped_already_processed']}")
    print(f"Files skipped (no <details> block found): {counts['skipped_no_details_block']}")
    print(f"Files skipped (no change needed/empty block/no refs parsed/no new content): {counts['skipped_no_change_needed'] + counts['skipped_no_textual_change']}") # Simplified summary for other skips
    print(f"Files not found: {counts['file_not_found']}")
    print(f"Read errors: {counts['error_read']}")
    print(f"Write errors: {counts['error_write']}")
    print("Full script execution with 'Sens' logic complete. Review logs for details.")
