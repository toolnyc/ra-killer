"""Tests that previously demonstrated normalization gaps, now fixed.

These tests verify the improved normalization catches cross-source
inconsistencies in venue names, artist qualifiers, and taste matching.
"""

from datetime import date

from src.models import Event, ScrapedEvent, Source, TasteEntry
from src.normalize import normalize, normalize_venue
from src.recommend.taste import TasteProfile
from src.scrapers.runner import artist_jaccard, is_fuzzy_match


# ────────────────────────────────────────────────────────────────────
#  Venue aliases — same physical venue, different names
# ────────────────────────────────────────────────────────────────────


class TestVenueAliases:
    """The same venue often has different names across sources."""

    def test_the_prefix(self):
        assert normalize_venue("The Lot Radio") == normalize_venue("Lot Radio")

    def test_suffix_variations(self):
        assert normalize_venue("Basement") == normalize_venue("Basement NY")

    def test_venue_with_neighborhood(self):
        assert normalize_venue("Good Room") == normalize_venue("Good Room Brooklyn")

    def test_venue_ampersand_vs_and(self):
        assert normalize_venue("Light & Sound") == normalize_venue("Light and Sound")

    def test_venue_fuzzy_match_with_alias(self):
        """Fuzzy matching now handles venue suffix differences."""
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
        assert is_fuzzy_match(scraped, existing) is True


# ────────────────────────────────────────────────────────────────────
#  Artist performance qualifiers
# ────────────────────────────────────────────────────────────────────


class TestArtistQualifiers:
    """Performance qualifiers like (Live), (DJ Set) no longer break Jaccard."""

    def test_live_qualifier(self):
        assert artist_jaccard(["DJ Harvey (Live)"], ["DJ Harvey"]) == 1.0

    def test_dj_set_qualifier(self):
        assert artist_jaccard(["Bicep (DJ Set)"], ["Bicep"]) == 1.0

    def test_b2b_qualifier(self):
        score = artist_jaccard(
            ["Sama' Abdulhadi b2b Héctor Oaks"],
            ["Sama' Abdulhadi", "Héctor Oaks"],
        )
        assert score > 0.5

    def test_ampersand_friends(self):
        assert artist_jaccard(["Honey Dijon & friends"], ["Honey Dijon"]) == 1.0

    def test_presents(self):
        assert artist_jaccard(["DJ Koze"], ["Rinsed presents: DJ Koze"]) > 0.0


# ────────────────────────────────────────────────────────────────────
#  Title normalization (base normalize — already worked)
# ────────────────────────────────────────────────────────────────────


class TestTitleNormalization:
    def test_em_dash_vs_hyphen(self):
        assert normalize("Event \u2013 Night") == normalize("Event - Night")
        assert normalize("Event \u2014 Night") == normalize("Event - Night")

    def test_smart_quotes(self):
        assert normalize("\u201cEvent\u201d") == normalize('"Event"')


# ────────────────────────────────────────────────────────────────────
#  Taste profile matching now uses full normalization
# ────────────────────────────────────────────────────────────────────


class TestTasteMatching:
    def test_taste_accent_mismatch(self):
        taste = TasteProfile(entries=[
            TasteEntry(category="artist", name="Nina Kraviz", weight=2.0),
        ])
        assert taste.artist_weight("Nina Kravíz") > 0

    def test_taste_extra_whitespace(self):
        taste = TasteProfile(entries=[
            TasteEntry(category="venue", name="Nowadays", weight=1.5),
        ])
        assert taste.venue_weight("Nowadays ") > 0

    def test_taste_punctuation(self):
        taste = TasteProfile(entries=[
            TasteEntry(category="artist", name="Sama' Abdulhadi", weight=2.0),
        ])
        assert taste.artist_weight("Sama Abdulhadi") > 0


# ────────────────────────────────────────────────────────────────────
#  Cross-source dedup end-to-end
# ────────────────────────────────────────────────────────────────────


class TestCrossSourceDedup:
    def test_ra_vs_dice_same_event(self):
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
        jaccard = artist_jaccard(ra_event.artists, dice_event.artists)
        assert jaccard > 0.5, f"Artist Jaccard was only {jaccard}"

    def test_elsewhere_vs_elsewhere_zone(self):
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
