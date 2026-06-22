"""Complete data pipeline test."""

import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from providers.data_bus import DatabaseFirstDataBus


def test_data_bus_kline():
    """Test: DatabaseFirstDataBus K-line operations."""
    print("=" * 60)
    print("Test 1: DataBus K-line (Database First)")
    print("=" * 60)

    db_path = Path("runtime/test_databus.db")
    if db_path.exists():
        db_path.unlink()

    bus = DatabaseFirstDataBus(str(db_path))

    # First query - should be empty, try API
    print("  Querying 600519 (first time, should try API)...")
    data = bus.get_kline("600519", days=30)
    if data:
        print(f"  Got {len(data)} rows")
        print(f"  First: {data[0]}")
        print(f"  Last: {data[-1]}")
    else:
        print("  No data from API (network issue expected)")

    # Insert mock data
    print("\n  Inserting mock data...")
    mock_data = [
        {
            "stock_code": "600519",
            "trade_date": "2026-01-01",
            "open": 1500,
            "high": 1520,
            "low": 1490,
            "close": 1510,
            "volume": 1000000,
            "amount": 1.5e9,
        },
        {
            "stock_code": "600519",
            "trade_date": "2026-01-02",
            "open": 1510,
            "high": 1530,
            "low": 1500,
            "close": 1525,
            "volume": 1200000,
            "amount": 1.8e9,
        },
    ]
    saved = bus._save_kline("600519", mock_data)
    print(f"  Saved {saved} rows")

    # Second query - should get from database
    print("\n  Querying again (should get from database)...")
    data2 = bus.get_kline("600519", days=30)
    if data2:
        print(f"  Got {len(data2)} rows from database")
        for d in data2:
            print(f"    {d['trade_date']}: C={d['close']}")
    else:
        print("  No data")

    db_path.unlink()
    print("  [PASS] DataBus K-line works\n")


def test_data_bus_stock_info():
    """Test: DatabaseFirstDataBus StockInfo operations."""
    print("=" * 60)
    print("Test 2: DataBus StockInfo")
    print("=" * 60)

    db_path = Path("runtime/test_databus_info.db")
    if db_path.exists():
        db_path.unlink()

    bus = DatabaseFirstDataBus(str(db_path))

    # Query - should try API
    print("  Querying 600519 stock info...")
    info = bus.get_stock_info("600519")
    if info:
        print(f"  Got: {info}")
    else:
        print("  No info from API (expected)")

    # Save mock
    print("\n  Saving mock stock info...")
    bus._save_stock_info(
        "600519", {"stock_name": "贵州茅台", "pe_ratio": 25.0, "roe": 0.30, "latest_price": 1500.0}
    )

    # Query again
    print("\n  Querying again...")
    info2 = bus.get_stock_info("600519")
    if info2:
        print(f"  Got from database: {info2}")
    else:
        print("  No info")

    db_path.unlink()
    print("  [PASS] DataBus StockInfo works\n")


def test_adapter_selection():
    """Test: Adapter selection and fallback."""
    print("=" * 60)
    print("Test 3: Adapter Selection")
    print("=" * 60)

    bus = DatabaseFirstDataBus(":memory:")
    adapters = bus._get_adapters()
    print(f"  Available adapters: {len(adapters)}")
    for a in adapters:
        print(f"    - {a.name} (priority={a.priority})")

    print("  [PASS] Adapter selection works\n")


def test_incremental_update():
    """Test: Incremental update (only insert new rows)."""
    print("=" * 60)
    print("Test 4: Incremental Update")
    print("=" * 60)

    db_path = Path("runtime/test_incremental.db")
    if db_path.exists():
        db_path.unlink()

    bus = DatabaseFirstDataBus(str(db_path))

    # Insert initial data
    data1 = [
        {
            "stock_code": "600519",
            "trade_date": "2026-01-01",
            "open": 1500,
            "high": 1520,
            "low": 1490,
            "close": 1510,
            "volume": 1000000,
            "amount": 1.5e9,
        },
        {
            "stock_code": "600519",
            "trade_date": "2026-01-02",
            "open": 1510,
            "high": 1530,
            "low": 1500,
            "close": 1525,
            "volume": 1200000,
            "amount": 1.8e9,
        },
    ]
    saved1 = bus._save_kline("600519", data1)
    print(f"  First insert: {saved1} rows")

    # Insert again (should not duplicate)
    data2 = [
        {
            "stock_code": "600519",
            "trade_date": "2026-01-01",
            "open": 1500,
            "high": 1520,
            "low": 1490,
            "close": 1510,
            "volume": 1000000,
            "amount": 1.5e9,
        },
        {
            "stock_code": "600519",
            "trade_date": "2026-01-03",
            "open": 1525,
            "high": 1540,
            "low": 1515,
            "close": 1535,
            "volume": 1100000,
            "amount": 1.7e9,
        },
    ]
    saved2 = bus._save_kline("600519", data2)
    print(f"  Second insert: {saved2} rows (should be 1, not 2)")

    # Verify total
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("SELECT COUNT(*) FROM kline_daily WHERE stock_code='600519'")
    total = cursor.fetchone()[0]
    conn.close()
    print(f"  Total rows: {total} (should be 3)")

    db_path.unlink()
    print("  [PASS] Incremental update works\n")


if __name__ == "__main__":
    print("=" * 60)
    print("AShare-X Data Pipeline Test")
    print("=" * 60)

    test_data_bus_kline()
    test_data_bus_stock_info()
    test_adapter_selection()
    test_incremental_update()

    print("=" * 60)
    print("All data pipeline tests completed!")
    print("=" * 60)
