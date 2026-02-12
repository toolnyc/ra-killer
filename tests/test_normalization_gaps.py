"""Tests demonstrating normalization gaps in the current dedup system.

Each test is categorized by the type of gap:
  - VENUE: same physical venue, different string representations
  - ARTIST: same DJ/artist, different string representations
  - TITLE: same event, title variations across sources
  - TASTE: taste profile matching misses due to weaker normalization
  - QUALIFIER: artist performance qualifiers causing false negatives
"""

from datetime import date

import pytest

from src.models import Event, ScrapedEvent, Source
from src.scrapers.runner import artist_jaccard, is_fuzzy_match, normalize


# ────────────────────────────────────────────────────────────────────
#  GAP 1: Venue aliases — same physical venue, different names
# ────────────────────────────────────────────────────────────────────


class TestVenueAliases:
    """The same venue often has different names across sources."""

    def test_the_prefix(self):
        """'The Lot Radio' (RA) vs 'Lot Radio' (NYC Noise)"""
        # Current: normalize keeps 'the', so these DON'T match
        assert normalize("The Lot Radio") == normalize("Lot Radio")

    def test_suffix_variations(self):
        """'Basement' (DICE) vs 'Basement NY' (own site)"""
        assert normalize("Basement") == normalize("Basement NY")

    def test_venue_with_neighborhood(self):
        """'Good Room' vs 'Good Room Brooklyn'"""
        assert normalize("Good Room") == normalize("Good Room Brooklyn")

    def test_venue_punctuation(self):
        """'Goodroom' vs 'Good Room' — no punctuation to strip, space matters"""
        # These are the SAME venue but written differently
        # token_sort_ratio would catch this (~83), but exact-key match won't
        assert normalize("Goodroom") == normalize("Good Room")

    def test_venue_ampersand_vs_and(self):
        """'Light & Sound' vs 'Light and Sound'"""
        # Current: normalize strips '&' but keeps 'and'
        assert normalize("Light & Sound") == normalize("Light and Sound")

    def test_venue_abbreviation(self):
        """'Market Hotel' vs 'Mkt Hotel'"""
        # This one's probably out of scope for simple normalization
        pass

    def test_venue_fuzzy_match_with_alias(self):
        """Even fuzzy matching fails for very different venue representations."""
        scraped = ScrapedEvent(
            source=Source.DICE,
            source_id="1",
            title="Honey Dijon",
            event_date=date(2025, 3, 15),
            venue_name="Basement",
            artists=["Honey Dijon"],
        )
        existing = Event(
            id="abc",
            title="Honey Dijon",
            event_date=date(2025, 3, 15),
            venue_name="Basement NY",
            artists=["Honey Dijon"],
        )
        # Title + artists match, venue should too (same place!)
        assert is_fuzzy_match(scraped, existing) is True


# ────────────────────────────────────────────────────────────────────
#  GAP 2: Artist performance qualifiers
# ────────────────────────────────────────────────────────────────────


class TestArtistQualifiers:
    """Performance qualifiers like (Live), (DJ Set) cause Jaccard mismatches."""

    def test_live_qualifier(self):
        """'DJ Harvey (Live)' should match 'DJ Harvey'."""
        # Current: normalize("DJ Harvey (Live)") == "dj harvey live"
        #          normalize("DJ Harvey") == "dj harvey"
        # These are NOT equal, so Jaccard treats them as different artists
        assert artist_jaccard(["DJ Harvey (Live)"], ["DJ Harvey"]) == 1.0

    def test_dj_set_qualifier(self):
        """'Bicep (DJ Set)' should match 'Bicep'."""
        assert artist_jaccard(["Bicep (DJ Set)"], ["Bicep"]) == 1.0

    def test_b2b_qualifier(self):
        """'Sama' Abdulhadi b2b Héctor Oaks' — b2b could be one artist entry."""
        # Some sources list 'b2b' pairs as a single artist string
        score = artist_jaccard(
            ["Sama' Abdulhadi b2b Héctor Oaks"],
            ["Sama' Abdulhadi", "Héctor Oaks"],
        )
        assert score > 0.5

    def test_ampersand_friends(self):
        """'Honey Dijon & friends' vs just 'Honey Dijon'."""
        assert artist_jaccard(["Honey Dijon & friends"], ["Honey Dijon"]) == 1.0

    def test_presents(self):
        """'Rinsed presents: DJ Koze' — 'presents' in artist name."""
        # Some sources put the promoter in the artist field
        assert artist_jaccard(["DJ Koze"], ["Rinsed presents: DJ Koze"]) > 0.0


# ────────────────────────────────────────────────────────────────────
#  GAP 3: Title noise words
# ────────────────────────────────────────────────────────────────────


class TestTitleNormalization:
    """Titles contain venue references, prepositions, and promoter branding."""

    def test_at_vs_bare(self):
        """'Honey Dijon at Nowadays' vs 'Honey Dijon' (different sources)."""
        # RA often uses "Artist at Venue" format while DICE just uses the event name
        score = normalize("Honey Dijon at Nowadays")
        assert score != normalize("Honey Dijon")
        # The fuzzy matcher handles this via token_sort_ratio, but exact-key match fails

    def test_presents_in_title(self):
        """'Nowadays presents: Honey Dijon' vs 'Honey Dijon at Nowadays'."""
        # These are the same event — normalize can't handle this alone,
        # but we could strip 'presents:' prefix

    def test_em_dash_vs_hyphen(self):
        """Unicode dashes should normalize to same thing."""
        # en-dash, em-dash, minus vs ASCII hyphen
        assert normalize("Event \u2013 Night") == normalize("Event - Night")
        assert normalize("Event \u2014 Night") == normalize("Event - Night")

    def test_smart_quotes(self):
        """Smart quotes from copy-paste should normalize."""
        assert normalize("\u201cEvent\u201d") == normalize('"Event"')


# ────────────────────────────────────────────────────────────────────
#  GAP 4: Taste profile matching uses weaker normalization
# ────────────────────────────────────────────────────────────────────


class TestTasteMatchingGaps:
    """taste.py only uses .lower() while dedup uses full normalize()."""

    def test_taste_accent_mismatch(self):
        """If taste has 'nina kraviz' but event has 'Nina Kravíz', .lower() fails."""
        from src.recommend.taste import TasteProfile
        from src.models import TasteEntry

        taste = TasteProfile(entries=[
            TasteEntry(category="artist", name="Nina Kraviz", weight=2.0),
        ])
        # Scraper might preserve accented source data
        assert taste.artist_weight("Nina Kravíz") > 0

    def test_taste_extra_whitespace(self):
        """Trailing space in scraper output breaks .lower() match."""
        from src.recommend.taste import TasteProfile
        from src.models import TasteEntry

        taste = TasteProfile(entries=[
            TasteEntry(category="venue", name="Nowadays", weight=1.5),
        ])
        # NYC Noise's venue extraction could leave trailing spaces
        assert taste.venue_weight("Nowadays ") > 0

    def test_taste_punctuation(self):
        """Punctuation in artist name breaks simple .lower() match."""
        from src.recommend.taste import TasteProfile
        from src.models import TasteEntry

        taste = TasteProfile(entries=[
            TasteEntry(category="artist", name="Sama' Abdulhadi", weight=2.0),
        ])
        # Another source might omit the apostrophe
        assert taste.artist_weight("Sama Abdulhadi") > 0


# ────────────────────────────────────────────────────────────────────
#  GAP 5: Cross-source dedup end-to-end failures
# ────────────────────────────────────────────────────────────────────


class TestCrossSourceDedup:
    """Real-world-ish scenarios where dedup should merge but doesn't."""

    def test_ra_vs_dice_same_event(self):
        """RA and DICE format the same event differently."""
        ra_event = ScrapedEvent(
            source=Source.RA,
            source_id="ra-1",
            title="Honey Dijon All Night Long",
            event_date=date(2025, 3, 15),
            venue_name="Nowadays",
            artists=["Honey Dijon"],
        )
        dice_event = Event(
            id="dice-1",
            title="Honey Dijon: All Night Long at Nowadays",
            event_date=date(2025, 3, 15),
            venue_name="Nowadays",
            artists=["Honey Dijon"],
            sources=["dice"],
        )
        assert is_fuzzy_match(ra_event, dice_event) is True

    def test_event_with_qualifier_artists(self):
        """Same event but artists listed with qualifiers on one source."""
        ra_event = ScrapedEvent(
            source=Source.RA,
            source_id="ra-2",
            title="Panorama Bar Night",
            event_date=date(2025, 4, 1),
            venue_name="Elsewhere",
            artists=["Bicep (DJ Set)", "Peggy Gou (Live)"],
        )
        dice_event = Event(
            id="dice-2",
            title="Panorama Bar Night",
            event_date=date(2025, 4, 1),
            venue_name="Elsewhere",
            artists=["Bicep", "Peggy Gou"],
            sources=["dice"],
        )
        # Title matches, venue matches. But do artists match?
        jaccard = artist_jaccard(ra_event.artists, dice_event.artists)
        assert jaccard > 0.5, f"Artist Jaccard was only {jaccard}"

    def test_elsewhere_vs_elsewhere_zone(self):
        """Elsewhere has multiple rooms that sources name differently."""
        scraped = ScrapedEvent(
            source=Source.DICE,
            source_id="d-1",
            title="Some Party",
            event_date=date(2025, 3, 20),
            venue_name="Elsewhere - Zone One",
            artists=["DJ A"],
        )
        existing = Event(
            id="e-1",
            title="Some Party",
            event_date=date(2025, 3, 20),
            venue_name="Elsewhere",
            artists=["DJ A"],
            sources=["ra"],
        )
        assert is_fuzzy_match(scraped, existing) is True
