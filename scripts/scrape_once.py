#!/usr/bin/env python3
"""One-shot scrape: run all scrapers, deduplicate, store to Supabase."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scrapers.runner import run_scrape_pipeline


async def main():
    print("Starting one-shot scrape...")
    new_count = await run_scrape_pipeline()
    print(f"Done! {new_count} new canonical events stored.")


if __name__ == "__main__":
    asyncio.run(main())
