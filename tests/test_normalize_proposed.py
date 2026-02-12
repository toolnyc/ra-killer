"""Tests for the proposed improved normalization functions."""

from src.normalize import (
    normalize,
    normalize_artist,
    normalize_artist_list,
    normalize_venue,
    split_artist_entry,
)


# ── Base normalize (unchanged behavior) ─────────────────────────────


class TestBaseNormalize:
    def test_basic(self):
        assert normalize("Hello World!") == "hello world"

    def test_accents(self):
        assert normalize("café") == "cafe"
        assert normalize("Héctor") == "hector"

    def test_unicode_dashes(self):
        """NFKD decomposes em-dash/en-dash to punctuation, which gets stripped."""
        assert normalize("Event \u2013 Night") == normalize("Event - Night")
        assert normalize("Event \u2014 Night") == normalize("Event - Night")

    def test_smart_quotes(self):
        assert normalize("\u201cEvent\u201d") == normalize('"Event"')

    def test_collapse_whitespace(self):
        assert normalize("  multiple   spaces  ") == "multiple spaces"


# ── Venue normalization ─────────────────────────────────────────────


class TestNormalizeVenue:
    def test_the_prefix(self):
        assert normalize_venue("The Lot Radio") == normalize_venue("Lot Radio")

    def test_the_prefix_preserved_in_middle(self):
        """'the' in the middle of a name should stay."""
        assert "the" in normalize_venue("Under the K Bridge")

    def test_suffix_ny(self):
        assert normalize_venue("Basement NY") == normalize_venue("Basement")

    def test_suffix_brooklyn(self):
        assert normalize_venue("Good Room Brooklyn") == normalize_venue("Good Room")

    def test_suffix_nyc(self):
        assert normalize_venue("Venue NYC") == normalize_venue("Venue")

    def test_ampersand_vs_and(self):
        assert normalize_venue("Light & Sound") == normalize_venue("Light and Sound")

    def test_zone_qualifier(self):
        assert normalize_venue("Elsewhere - Zone One") == normalize_venue("Elsewhere")

    def test_room_qualifier(self):
        assert normalize_venue("Basement - Studio") == normalize_venue("Basement")

    def test_preserves_meaningful_names(self):
        """Make sure we don't over-strip."""
        assert normalize_venue("Nowadays") == "nowadays"
        assert normalize_venue("Good Room") == "good room"
        assert normalize_venue("Market Hotel") == "market hotel"


# ── Artist normalization ────────────────────────────────────────────


class TestNormalizeArtist:
    def test_live_qualifier(self):
        assert normalize_artist("DJ Harvey (Live)") == normalize_artist("DJ Harvey")

    def test_dj_set_qualifier(self):
        assert normalize_artist("Bicep (DJ Set)") == normalize_artist("Bicep")

    def test_all_night_long(self):
        assert normalize_artist("Honey Dijon (All Night Long)") == normalize_artist("Honey Dijon")

    def test_b2b_qualifier_in_parens(self):
        assert normalize_artist("Artist (B2B Someone)") == normalize_artist("Artist")

    def test_and_friends(self):
        assert normalize_artist("Honey Dijon & friends") == normalize_artist("Honey Dijon")

    def test_presents_prefix(self):
        assert normalize_artist("Rinsed presents: DJ Koze") == normalize_artist("DJ Koze")

    def test_preserves_core_name(self):
        assert normalize_artist("Sama' Abdulhadi") == "sama abdulhadi"
        assert normalize_artist("DJ Harvey") == "dj harvey"


# ── Artist list handling ────────────────────────────────────────────


class TestArtistList:
    def test_b2b_split(self):
        result = split_artist_entry("Sama' Abdulhadi b2b Héctor Oaks")
        assert len(result) == 2
        assert "sama abdulhadi" in result
        assert "hector oaks" in result

    def test_b2b_uppercase(self):
        result = split_artist_entry("DJ A B2B DJ B")
        assert len(result) == 2

    def test_no_split_needed(self):
        result = split_artist_entry("Honey Dijon")
        assert result == ["honey dijon"]

    def test_normalize_artist_list_with_qualifiers_and_b2b(self):
        artists = [
            "Bicep (DJ Set)",
            "Sama' Abdulhadi b2b Héctor Oaks",
            "Peggy Gou (Live)",
        ]
        result = normalize_artist_list(artists)
        expected = {"bicep", "sama abdulhadi", "hector oaks", "peggy gou"}
        assert result == expected

    def test_jaccard_with_normalized_lists(self):
        """The improved normalization fixes the Jaccard gap."""
        list_a = ["Bicep (DJ Set)", "Peggy Gou (Live)"]
        list_b = ["Bicep", "Peggy Gou"]
        set_a = normalize_artist_list(list_a)
        set_b = normalize_artist_list(list_b)
        intersection = set_a & set_b
        union = set_a | set_b
        jaccard = len(intersection) / len(union)
        assert jaccard == 1.0

    def test_jaccard_b2b_overlap(self):
        """b2b entry on one side, individual entries on the other."""
        list_a = ["Sama' Abdulhadi b2b Héctor Oaks"]
        list_b = ["Sama' Abdulhadi", "Héctor Oaks"]
        set_a = normalize_artist_list(list_a)
        set_b = normalize_artist_list(list_b)
        intersection = set_a & set_b
        union = set_a | set_b
        jaccard = len(intersection) / len(union)
        assert jaccard == 1.0
