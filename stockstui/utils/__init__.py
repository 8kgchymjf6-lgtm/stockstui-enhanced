def slugify(name: str) -> str:
    """Converts a string to a snake_case identifier, safe for use as a file or category name."""
    return name.strip().lower().replace(" ", "_")


def extract_cell_text(cell) -> str:
    """
    Safely extracts the plain text content from a Rich renderable or a DataTable cell.

    Args:
        cell: The cell or renderable object.

    Returns:
        The extracted plain text as a string.
    """
    if not cell:
        return ""
    # Prefer the .plain attribute for Rich objects, fall back to str()
    return getattr(cell, "plain", str(cell)).strip()


def parse_tags(tags_input: str) -> list[str]:
    """
    Parses a tag input string that can use space, comma, or semicolon separators.

    Args:
        tags_input: String containing tags separated by spaces, commas, or semicolons

    Returns:
        List of cleaned, deduplicated tags
    """
    if not tags_input or not tags_input.strip():
        return []

    # Replace semicolons and commas with spaces for unified splitting
    normalized = tags_input.replace(";", " ").replace(",", " ")

    # Split by whitespace and clean up
    tags = [tag.strip().lower() for tag in normalized.split() if tag.strip()]

    # Remove duplicates while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)

    return unique_tags


def format_tags(tags: list[str]) -> str:
    """
    Formats a list of tags back to a comma-separated string for display.

    Args:
        tags: List of tag strings

    Returns:
        Comma-separated string of tags
    """
    if not tags:
        return ""
    return ", ".join(tags)


def match_tags(item_tags: list[str], filter_tags: list[str]) -> bool:
    """
    Checks if any of the filter tags match the item's tags.

    Args:
        item_tags: Tags associated with the item
        filter_tags: Tags to filter by

    Returns:
        True if any filter tag matches any item tag, False otherwise
    """
    if not filter_tags:
        return True  # No filter means show all

    if not item_tags:
        return False  # Hide untagged items when filtering for specific tags

    return bool(set(item_tags) & set(filter_tags))


def merge_price_data(existing: dict, new_data: dict) -> dict:
    """
    Merges new stock data into existing cached stock data using a merge-on-update strategy.
    
    This function separates 'ephemeral' live data from 'static' metadata and prevents
    overwriting valid cached values (like all_time_high) with None or missing values, which
    causes "N/A" display corruption.

    Args:
        existing: The dictionary containing the current cached stock fields.
        new_data: The dictionary containing the newly fetched fields.

    Returns:
        A new dictionary with the merged fields.
    """
    merged = existing.copy()

    # Iterate through all fields provided in the update.
    for k, v in new_data.items():
        if v is not None:
            if k == "all_time_high":
                # Special handling for all_time_high:
                # Retain the existing all_time_high unless the new value is a valid positive number
                # and either surpasses the old high or is the first valid high being recorded.
                try:
                    new_ath = float(v)
                    if new_ath > 0:
                        existing_ath = merged.get("all_time_high")
                        if existing_ath is not None:
                            try:
                                existing_ath_val = float(existing_ath)
                                # Keep the maximum to prevent corruption from stale/incomplete API data.
                                # ASSUMPTION: All-time highs generally do not decrease, except on stock splits
                                # which we accept if the new value is definitive and higher, or if we need to adjust.
                                # But to prevent temporary API glitch overwrites, we default to the higher value.
                                if new_ath > existing_ath_val:
                                    merged[k] = new_ath
                            except (ValueError, TypeError):
                                merged[k] = new_ath
                        else:
                            merged[k] = new_ath
                except (ValueError, TypeError):
                    pass
            else:
                # For all other fields, if they are not None, we update the cache.
                merged[k] = v

    # Definitive invalidation check for all_time_high:
    # If the new price, day_high, or fifty_two_week_high exceeds the cached all_time_high,
    # the existing all_time_high is definitively invalid because the price reached a new peak.
    # We update all_time_high to match the new highest recorded value.
    existing_ath = merged.get("all_time_high")
    if existing_ath is not None:
        try:
            existing_ath_val = float(existing_ath)
            current_max = existing_ath_val
            for field in ["price", "day_high", "fifty_two_week_high"]:
                val = merged.get(field)
                if val is not None:
                    try:
                        val_float = float(val)
                        if val_float > current_max:
                            current_max = val_float
                    except (ValueError, TypeError):
                        pass
            if current_max > existing_ath_val:
                merged["all_time_high"] = current_max
        except (ValueError, TypeError):
            pass

    return merged

