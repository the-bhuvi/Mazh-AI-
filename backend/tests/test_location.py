import pytest
import asyncio
from app.location import get_lat_lon_from_pin, get_lat_lon_from_place, reverse_geocode

@pytest.mark.asyncio
async def test_known_pin_lookup():
    res = await get_lat_lon_from_pin("600001")
    assert res["lat"] == pytest.approx(13.0827, rel=1e-2)
    assert res["lon"] == pytest.approx(80.2707, rel=1e-2)
    assert "Chennai" in res["name"] or "Parrys" in res["name"]

@pytest.mark.asyncio
async def test_invalid_pin_format():
    with pytest.raises(ValueError):
        await get_lat_lon_from_pin("ABC123")

@pytest.mark.asyncio
async def test_unknown_pin_lookup():
    # Invalid non-existent PIN code 000000
    with pytest.raises(ValueError):
        await get_lat_lon_from_pin("000000")

@pytest.mark.asyncio
async def test_place_geocoding():
    res = await get_lat_lon_from_place("Madurai")
    assert res["lat"] == pytest.approx(9.9252, rel=0.1)
    assert res["lon"] == pytest.approx(78.1198, rel=0.1)

@pytest.mark.asyncio
async def test_reverse_geocoding():
    name = await reverse_geocode(13.0827, 80.2707)
    assert isinstance(name, str)
    assert len(name) > 0
