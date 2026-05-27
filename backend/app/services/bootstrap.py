from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import Base, engine
from app.models import Asset, AssetGroup, Branch, ModelConfig, User
from app.services.security import hash_password


BRANCHES = [
    ("human_scored", "Human Scored", "Only manually scored event clusters enter forecasts."),
    ("model_scored", "Model Scored", "Event clusters are scored automatically by models."),
]

MODEL_ROLES = [
    ("neutral_extractor", "openai", "gpt-4.1-mini"),
    ("auto_scorer", "openai", "gpt-4.1-mini"),
    ("macro_asset_model", "openai", "gpt-4.1"),
    ("industry_sector_model", "openai", "gpt-4.1"),
    ("market_trading_model", "openai", "gpt-4.1"),
    ("judge_aggregator", "openai", "gpt-4.1"),
]

ASSET_GROUPS = [
    {
        "name": "US Dollar Index",
        "slug": "us-dollar-index",
        "category": "macro",
        "region": "global",
        "assets": [("DX-Y.NYB", "DXY", "global", "index", "primary")],
    },
    {
        "name": "US 10Y Treasury Yield",
        "slug": "us-10y-treasury-yield",
        "category": "macro",
        "region": "us",
        "assets": [("^TNX", "US 10Y Yield", "us", "rate", "primary")],
    },
    {
        "name": "Gold",
        "slug": "gold",
        "category": "macro",
        "region": "global",
        "assets": [("GLD", "SPDR Gold Shares", "us", "etf", "primary")],
    },
    {
        "name": "Crude Oil",
        "slug": "crude-oil",
        "category": "macro",
        "region": "global",
        "assets": [("USO", "United States Oil Fund", "us", "etf", "primary")],
    },
    {
        "name": "Copper",
        "slug": "copper",
        "category": "macro",
        "region": "global",
        "assets": [("CPER", "United States Copper Index Fund", "us", "etf", "primary")],
    },
    {
        "name": "BTC",
        "slug": "btc",
        "category": "macro",
        "region": "global",
        "assets": [("BTC-USD", "Bitcoin", "crypto", "crypto", "primary")],
    },
    {
        "name": "ETH",
        "slug": "eth",
        "category": "macro",
        "region": "global",
        "assets": [("ETH-USD", "Ethereum", "crypto", "crypto", "primary")],
    },
    {
        "name": "USD/CNH",
        "slug": "usd-cnh",
        "category": "macro",
        "region": "global",
        "assets": [("CNH=X", "USD/CNH", "global", "fx", "primary")],
    },
    {
        "name": "VIX",
        "slug": "vix",
        "category": "macro",
        "region": "us",
        "assets": [("^VIX", "CBOE Volatility Index", "us", "index", "primary")],
    },
    {
        "name": "S&P 500",
        "slug": "sp-500",
        "category": "index",
        "region": "us",
        "assets": [("SPY", "SPDR S&P 500 ETF", "us", "etf", "primary")],
    },
    {
        "name": "Nasdaq 100",
        "slug": "nasdaq-100",
        "category": "index",
        "region": "us",
        "assets": [("QQQ", "Invesco QQQ Trust", "us", "etf", "primary")],
    },
    {
        "name": "CSI 300",
        "slug": "csi-300",
        "category": "index",
        "region": "cn_hk",
        "assets": [("510300.SS", "CSI 300 ETF", "cn", "etf", "primary")],
    },
    {
        "name": "Hang Seng Tech",
        "slug": "hang-seng-tech",
        "category": "index",
        "region": "cn_hk",
        "assets": [("3067.HK", "Hang Seng Tech ETF", "hk", "etf", "primary")],
    },
    {
        "name": "Semiconductors",
        "slug": "semiconductors",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("SMH", "VanEck Semiconductor ETF", "us", "etf", "primary"),
            ("SOXX", "iShares Semiconductor ETF", "us", "etf", "supporting"),
            ("NVDA", "NVIDIA", "us", "stock", "supporting"),
            ("MU", "Micron", "us", "stock", "supporting"),
            ("512480.SS", "China Semiconductor ETF", "cn", "etf", "primary"),
        ],
    },
    {
        "name": "AI Compute and Data Centers",
        "slug": "ai-compute-data-centers",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("NVDA", "NVIDIA", "us", "stock", "primary"),
            ("AVGO", "Broadcom", "us", "stock", "supporting"),
            ("VRT", "Vertiv", "us", "stock", "supporting"),
            ("601138.SS", "Foxconn Industrial Internet", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Power and Utilities",
        "slug": "power-utilities",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("XLU", "Utilities Select Sector SPDR", "us", "etf", "primary"),
            ("NEE", "NextEra Energy", "us", "stock", "supporting"),
            ("600900.SS", "China Yangtze Power", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Grid Equipment",
        "slug": "grid-equipment",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("ETN", "Eaton", "us", "stock", "primary"),
            ("PWR", "Quanta Services", "us", "stock", "supporting"),
            ("600406.SS", "NARI Technology", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Nuclear Power",
        "slug": "nuclear-power",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("CCJ", "Cameco", "us", "stock", "primary"),
            ("URA", "Global X Uranium ETF", "us", "etf", "supporting"),
            ("601985.SS", "China National Nuclear Power", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Oil and Gas",
        "slug": "oil-gas",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("XLE", "Energy Select Sector SPDR", "us", "etf", "primary"),
            ("XOM", "Exxon Mobil", "us", "stock", "supporting"),
            ("600938.SS", "CNOOC China", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Gold and Precious Metals",
        "slug": "gold-precious-metals",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("GDX", "VanEck Gold Miners ETF", "us", "etf", "primary"),
            ("NEM", "Newmont", "us", "stock", "supporting"),
            ("601899.SS", "Zijin Mining", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Banks",
        "slug": "banks",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("XLF", "Financial Select Sector SPDR", "us", "etf", "primary"),
            ("JPM", "JPMorgan Chase", "us", "stock", "supporting"),
            ("600036.SS", "China Merchants Bank", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Defense",
        "slug": "defense",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("ITA", "iShares US Aerospace & Defense ETF", "us", "etf", "primary"),
            ("LMT", "Lockheed Martin", "us", "stock", "supporting"),
            ("600760.SS", "AVIC Shenyang Aircraft", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Innovative Drugs and Healthcare",
        "slug": "innovative-drugs-healthcare",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("XBI", "SPDR Biotech ETF", "us", "etf", "primary"),
            ("LLY", "Eli Lilly", "us", "stock", "supporting"),
            ("06160.HK", "BeiGene", "hk", "stock", "primary"),
        ],
    },
    {
        "name": "Nonferrous Metals and Copper",
        "slug": "nonferrous-metals-copper",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("COPX", "Global X Copper Miners ETF", "us", "etf", "primary"),
            ("FCX", "Freeport-McMoRan", "us", "stock", "supporting"),
            ("603993.SS", "CMOC", "cn", "stock", "primary"),
        ],
    },
    {
        "name": "Robotics and Automation",
        "slug": "robotics-automation",
        "category": "theme",
        "region": "cross_market",
        "assets": [
            ("BOTZ", "Global X Robotics & AI ETF", "us", "etf", "primary"),
            ("ROBO", "ROBO Global Robotics ETF", "us", "etf", "supporting"),
            ("300124.SZ", "Inovance Technology", "cn", "stock", "primary"),
        ],
    },
]


def create_database() -> None:
    Base.metadata.create_all(bind=engine)


def seed_database(db: Session, settings: Settings) -> None:
    seed_branches(db)
    seed_model_configs(db)
    seed_asset_universe(db)
    seed_admin(db, settings)


def seed_branches(db: Session) -> None:
    for name, display_name, description in BRANCHES:
        if db.scalar(select(Branch).where(Branch.name == name)):
            continue
        db.add(Branch(name=name, display_name=display_name, description=description))
    db.commit()


def seed_model_configs(db: Session) -> None:
    for role, provider, model_name in MODEL_ROLES:
        if db.scalar(select(ModelConfig).where(ModelConfig.role == role)):
            continue
        db.add(ModelConfig(role=role, provider=provider, model_name=model_name))
    db.commit()


def seed_asset_universe(db: Session) -> None:
    if db.scalar(select(AssetGroup).limit(1)):
        return

    for group_data in ASSET_GROUPS:
        group = AssetGroup(
            name=group_data["name"],
            slug=group_data["slug"],
            category=group_data["category"],
            region=group_data["region"],
            description=f"Seed universe group: {group_data['name']}",
        )
        db.add(group)
        db.flush()
        for symbol, display_name, market, asset_type, role in group_data["assets"]:
            db.add(
                Asset(
                    group_id=group.id,
                    symbol=symbol,
                    display_name=display_name,
                    market=market,
                    asset_type=asset_type,
                    role=role,
                    data_sources=["yfinance", "stooq"],
                )
            )
    db.commit()


def seed_admin(db: Session, settings: Settings) -> None:
    if db.scalar(select(User).where(User.username == settings.admin_bootstrap_user)):
        return

    if settings.admin_bootstrap_password_hash:
        password_hash = settings.admin_bootstrap_password_hash
    elif settings.admin_bootstrap_password:
        password_hash = hash_password(settings.admin_bootstrap_password)
    elif settings.environment == "development":
        password_hash = hash_password("admin")
    else:
        return

    db.add(User(username=settings.admin_bootstrap_user, password_hash=password_hash))
    db.commit()

