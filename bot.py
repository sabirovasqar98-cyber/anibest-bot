#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 ANIBEST BOT — To'liq O'zbek Tilida
Termux va Replit uchun tayyor

BOT_TOKEN va OWNER_ID qiymatlarini environment o'zgaruvchilari orqali bering.
"""

import os
import json
import re
import logging
import sqlite3
import time
import threading
import random
import unicodedata
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import telebot
from telebot import types


# Server UTC vaqtida ishlashi mumkin, lekin bot foydalanuvchilarga
# O'zbekiston (Toshkent) vaqtini ko'rsatadi. Bazadagi mavjud satrlar
# timezone-siz formatda saqlangani uchun helperlar ham naive local datetime
# qaytaradi.
LOCAL_TIMEZONE = ZoneInfo(os.environ.get("ANIBEST_TIMEZONE", "Asia/Tashkent"))


def local_now():
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)


def local_today():
    return local_now().date()

# ============================================================
#  SOZLAMALAR — FAQAT SHU 2 QATORNI TO'LDIRING
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = os.environ.get("OWNER_ID", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi. Termuxda ishga tushirishdan oldin "
        "export BOT_TOKEN='BotFather tokeni' buyrug'ini bering."
    )

try:
    OWNER_ID = int(OWNER_ID)
except (TypeError, ValueError) as exc:
    raise RuntimeError(
        "OWNER_ID topilmadi yoki noto'g'ri. Termuxda "
        "export OWNER_ID='Telegram ID' buyrug'ini bering."
    ) from exc

if OWNER_ID <= 0:
    raise RuntimeError("OWNER_ID musbat raqam bo'lishi kerak.")

CHANNEL_TAG = "@anibestrasmiy"
DEFAULT_CHANNEL_TAG = CHANNEL_TAG

# ============================================================
#  LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("anibest.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================
#  DATABASE
# ============================================================
DB = os.environ.get("ANIBEST_DB", "anibest.db")


def db():
    c = sqlite3.connect(DB, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    con = db()
    con.executescript(
        """
    CREATE TABLE IF NOT EXISTS users (
        user_id         INTEGER PRIMARY KEY,
        username        TEXT,
        full_name       TEXT,
        status          TEXT DEFAULT 'user',
        vip_expires     TEXT,
        premium_expires TEXT,
        coins           INTEGER DEFAULT 0,
        ref_code        TEXT UNIQUE,
        referred_by     INTEGER,
        last_bonus      TEXT,
        join_date       TEXT,
        last_active     TEXT,
        blocked         INTEGER DEFAULT 0,
        notifications_enabled INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS admins (
        user_id    INTEGER PRIMARY KEY,
        added_by   INTEGER,
        added_date TEXT
    );
    CREATE TABLE IF NOT EXISTS admin_permissions (
        user_id    INTEGER PRIMARY KEY,
        add_anime  INTEGER DEFAULT 0,
        add_media  INTEGER DEFAULT 0,
        add_ep     INTEGER DEFAULT 0,
        edit_anime INTEGER DEFAULT 0,
        del_anime  INTEGER DEFAULT 0,
        stats      INTEGER DEFAULT 0,
        broadcast  INTEGER DEFAULT 0,
        autopost   INTEGER DEFAULT 0,
        user_manage INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS anime (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        code        TEXT UNIQUE,
        title       TEXT,
        description TEXT,
        poster_id   TEXT,
        genres      TEXT,
        season      TEXT DEFAULT '1',
        ova_info    TEXT,
        voice       TEXT,
        min_status  TEXT DEFAULT 'user',
        age_limit   TEXT,
        episode_total TEXT,
        trailer_id  TEXT,
        trailer_type TEXT,
        views       INTEGER DEFAULT 0,
        added_by    INTEGER,
        added_date  TEXT
    );
    CREATE TABLE IF NOT EXISTS episodes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        anime_code  TEXT,
        ep_num      INTEGER,
        ep_type     TEXT DEFAULT 'season',
        file_id     TEXT,
        file_type   TEXT DEFAULT 'video',
        added_date  TEXT,
        UNIQUE(anime_code, ep_num, ep_type)
    );
    CREATE TABLE IF NOT EXISTS channels (
        channel_id   TEXT PRIMARY KEY,
        channel_name TEXT,
        channel_url  TEXT,
        platform     TEXT DEFAULT 'telegram',
        active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS autopost_channels (
        channel_id   TEXT PRIMARY KEY,
        channel_name TEXT,
        channel_url  TEXT,
        active       INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS autopost_settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    );
    CREATE TABLE IF NOT EXISTS spam_log (
        user_id   INTEGER PRIMARY KEY,
        last_time REAL DEFAULT 0,
        cnt       INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS autopost_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        anime_code      TEXT,
        anime_title     TEXT,
        post_type       TEXT,
        season          TEXT,
        ep_num          INTEGER,
        ep_type         TEXT,
        channel_id      TEXT,
        channel_name    TEXT,
        channel_url     TEXT,
        posted_by       INTEGER,
        posted_by_name  TEXT,
        posted_at       TEXT,
        message_id      INTEGER,
        status          TEXT,
        error           TEXT,
        text            TEXT,
        media_id        TEXT,
        media_type      TEXT,
        button_text     TEXT,
        genres          TEXT,
        voice           TEXT,
        min_status      TEXT
    );
    CREATE TABLE IF NOT EXISTS manual_posts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        text        TEXT NOT NULL,
        custom_text TEXT,
        post_type   TEXT DEFAULT 'new_anime',
        category    TEXT,
        image_id    TEXT,
        video_id    TEXT,
        audio_id    TEXT,
        age_limit   TEXT,
        anime_title TEXT,
        description TEXT,
        genres      TEXT,
        season      TEXT,
        episodes    TEXT,
        voice       TEXT,
        min_status  TEXT,
        anime_code  TEXT,
        channel_messages TEXT DEFAULT '{}',
        last_posted_at TEXT,
        created_by  INTEGER,
        created_at  TEXT,
        status      TEXT DEFAULT 'active'
    );
    CREATE TABLE IF NOT EXISTS manual_post_deliveries (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id      INTEGER NOT NULL,
        channel_id   TEXT NOT NULL,
        channel_name TEXT,
        message_id   INTEGER,
        media_type   TEXT,
        status       TEXT DEFAULT 'success',
        error        TEXT,
        posted_at    TEXT,
        updated_at   TEXT
    );
    CREATE TABLE IF NOT EXISTS favorites (
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        added_at   TEXT NOT NULL,
        PRIMARY KEY (user_id, anime_code)
    );
    CREATE TABLE IF NOT EXISTS watch_progress (
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        ep_type    TEXT NOT NULL DEFAULT 'season',
        ep_num     INTEGER NOT NULL,
        watched_at TEXT NOT NULL,
        PRIMARY KEY (user_id, anime_code, ep_type)
    );
    CREATE TABLE IF NOT EXISTS watch_history (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        ep_type    TEXT NOT NULL DEFAULT 'season',
        ep_num     INTEGER NOT NULL,
        watched_at TEXT NOT NULL,
        UNIQUE (user_id, anime_code, ep_type, ep_num)
    );
    CREATE TABLE IF NOT EXISTS anime_notifications (
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        enabled    INTEGER NOT NULL DEFAULT 1,
        added_at   TEXT NOT NULL,
        PRIMARY KEY (user_id, anime_code)
    );
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        ep_type    TEXT NOT NULL,
        ep_num     INTEGER NOT NULL,
        sent_at    TEXT NOT NULL,
        PRIMARY KEY (user_id, anime_code, ep_type, ep_num)
    );
    CREATE TABLE IF NOT EXISTS anime_view_dedupe (
        user_id    INTEGER NOT NULL,
        anime_code TEXT NOT NULL,
        viewed_date TEXT NOT NULL,
        viewed_at  TEXT NOT NULL,
        PRIMARY KEY (user_id, anime_code, viewed_date)
    );
    CREATE TABLE IF NOT EXISTS admin_actions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id   INTEGER NOT NULL,
        action     TEXT NOT NULL,
        anime_code TEXT,
        ep_type    TEXT,
        ep_num     INTEGER,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS media_categories (
        slug        TEXT PRIMARY KEY,
        title       TEXT NOT NULL,
        icon        TEXT DEFAULT '🎬',
        sort_order  INTEGER DEFAULT 0,
        active      INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS media_items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        media_type      TEXT NOT NULL,
        code            TEXT NOT NULL UNIQUE,
        title           TEXT NOT NULL,
        description     TEXT,
        poster_id       TEXT,
        main_media_id   TEXT,
        main_media_type TEXT,
        genres          TEXT,
        season          TEXT,
        episode_total   TEXT,
        age_limit       TEXT,
        trailer_id      TEXT,
        trailer_type    TEXT,
        voice           TEXT,
        min_status      TEXT DEFAULT 'user',
        views           INTEGER DEFAULT 0,
        added_by        INTEGER,
        added_date      TEXT,
        legacy_anime_id INTEGER,
        active          INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS media_parts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        media_id        INTEGER NOT NULL,
        part_type       TEXT NOT NULL DEFAULT 'part',
        season_number   INTEGER DEFAULT 1,
        part_number     INTEGER NOT NULL DEFAULT 1,
        title           TEXT,
        file_id         TEXT NOT NULL,
        file_type       TEXT NOT NULL DEFAULT 'document',
        added_by        INTEGER,
        added_date      TEXT,
        active          INTEGER DEFAULT 1,
        UNIQUE(media_id, part_type, season_number, part_number)
    );
    CREATE INDEX IF NOT EXISTS idx_media_parts_media
        ON media_parts(media_id, active, part_type, season_number, part_number);
    CREATE TABLE IF NOT EXISTS media_item_categories (
        media_id        INTEGER NOT NULL,
        category_slug   TEXT NOT NULL,
        sort_order      INTEGER DEFAULT 0,
        PRIMARY KEY(media_id, category_slug)
    );
    CREATE INDEX IF NOT EXISTS idx_media_item_categories_slug
        ON media_item_categories(category_slug, media_id);
    CREATE TABLE IF NOT EXISTS media_favorites (
        user_id         INTEGER NOT NULL,
        media_id        INTEGER NOT NULL,
        added_at        TEXT NOT NULL,
        PRIMARY KEY(user_id, media_id)
    );
    CREATE TABLE IF NOT EXISTS media_watch_progress (
        user_id         INTEGER NOT NULL,
        media_id        INTEGER NOT NULL,
        part_type       TEXT NOT NULL DEFAULT 'part',
        season_number   INTEGER DEFAULT 1,
        part_number     INTEGER NOT NULL,
        watched_at      TEXT NOT NULL,
        PRIMARY KEY(user_id, media_id, part_type, season_number)
    );
    CREATE TABLE IF NOT EXISTS media_watch_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL,
        media_id        INTEGER NOT NULL,
        part_type       TEXT NOT NULL DEFAULT 'part',
        season_number   INTEGER DEFAULT 1,
        part_number     INTEGER NOT NULL,
        watched_at      TEXT NOT NULL,
        UNIQUE(user_id, media_id, part_type, season_number, part_number)
    );
    CREATE TABLE IF NOT EXISTS media_notifications (
        user_id         INTEGER NOT NULL,
        media_id        INTEGER NOT NULL,
        enabled         INTEGER NOT NULL DEFAULT 1,
        added_at        TEXT NOT NULL,
        PRIMARY KEY(user_id, media_id)
    );
    CREATE TABLE IF NOT EXISTS media_notification_deliveries (
        user_id         INTEGER NOT NULL,
        media_id        INTEGER NOT NULL,
        part_type       TEXT NOT NULL DEFAULT 'part',
        season_number   INTEGER DEFAULT 1,
        part_number     INTEGER NOT NULL,
        sent_at         TEXT NOT NULL,
        PRIMARY KEY(user_id, media_id, part_type, season_number, part_number)
    );
    CREATE INDEX IF NOT EXISTS idx_media_items_type ON media_items(media_type, active);
    CREATE INDEX IF NOT EXISTS idx_media_items_title ON media_items(title);
    CREATE INDEX IF NOT EXISTS idx_media_items_views ON media_items(views DESC);
    """
    )
    con.commit()
    # Standart avtopost tugma matnini o'rnatish
    c = con.cursor()
    c.execute(
        "INSERT OR IGNORE INTO autopost_settings(key,value) VALUES(?,?)",
        ("watch_btn_text", "▶️ TOMOSHA QILISH"),
    )
    c.execute(
        "UPDATE autopost_settings SET value=? WHERE key=? AND value=?",
        ("▶️ TOMOSHA QILISH", "watch_btn_text", "✨ TOMOSHA QILISH ✨"),
    )
    c.execute(
        "INSERT OR IGNORE INTO autopost_settings(key,value) VALUES(?,?)",
        ("main_channel_tag", DEFAULT_CHANNEL_TAG),
    )
    con.commit()
    # Mavjud channels jadvaliga migration (platform va active ustunlari)
    c = con.cursor()
    try:
        c.execute("ALTER TABLE channels ADD COLUMN platform TEXT DEFAULT 'telegram'")
        con.commit()
    except Exception: pass
    try:
        c.execute("ALTER TABLE channels ADD COLUMN active INTEGER DEFAULT 1")
        con.commit()
    except Exception: pass
    # Yangi qo'lda post ruxsatlari uchun migration
    for mp_col in (
        "manual_post", "manual_post_history", "manual_post_edit",
        "manual_post_delete", "manual_post_repost", "user_manage", "add_media",
        "edit_media", "del_media",
    ):
        try:
            c.execute(f"ALTER TABLE admin_permissions ADD COLUMN {mp_col} INTEGER DEFAULT 0")
            con.commit()
        except Exception: pass

    c.execute("PRAGMA table_info(users)")
    existing_user_columns = {row["name"] for row in c.fetchall()}
    if "notifications_enabled" not in existing_user_columns:
        c.execute("ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
        con.commit()

    # Qo'lda postlarning yangi ma'lumotlari eski bazalarda ham xavfsiz qo'shiladi.
    anime_columns = {
        "age_limit": "TEXT",
        "episode_total": "TEXT",
        "trailer_id": "TEXT",
        "trailer_type": "TEXT",
    }
    c.execute("PRAGMA table_info(anime)")
    existing_anime_columns = {row["name"] for row in c.fetchall()}
    for column, definition in anime_columns.items():
        if column not in existing_anime_columns:
            c.execute(f"ALTER TABLE anime ADD COLUMN {column} {definition}")

    manual_columns = {
        "custom_text": "TEXT",
        "post_type": "TEXT DEFAULT 'new_anime'",
        "anime_title": "TEXT",
        "description": "TEXT",
        "genres": "TEXT",
        "season": "TEXT",
        "episodes": "TEXT",
        "voice": "TEXT",
        "min_status": "TEXT",
        "anime_code": "TEXT",
        "channel_messages": "TEXT DEFAULT '{}'",
        "last_posted_at": "TEXT",
    }
    c.execute("PRAGMA table_info(manual_posts)")
    existing_manual_columns = {row["name"] for row in c.fetchall()}
    for column, definition in manual_columns.items():
        if column not in existing_manual_columns:
            c.execute(f"ALTER TABLE manual_posts ADD COLUMN {column} {definition}")
    c.execute("PRAGMA table_info(autopost_history)")
    existing_history_columns = {row["name"] for row in c.fetchall()}
    if "message_id" not in existing_history_columns:
        c.execute("ALTER TABLE autopost_history ADD COLUMN message_id INTEGER")
    # Universal media platform migration. Eski anime jadvallari saqlanadi.
    for media_col, definition in (
        ("main_media_id", "TEXT"),
        ("main_media_type", "TEXT"),
        ("legacy_anime_id", "INTEGER"),
        ("active", "INTEGER DEFAULT 1"),
    ):
        try:
            c.execute(f"ALTER TABLE media_items ADD COLUMN {media_col} {definition}")
        except Exception:
            pass
    seed_media_categories(c)
    # Eski anime yozuvlarini universal katalogga faqat yetishmayotganlari uchun
    # ko'chiramiz. Mavjud anime/episodes ma'lumotlari o'zgartirilmaydi.
    c.execute(
        """INSERT OR IGNORE INTO media_items
           (media_type,code,title,description,poster_id,genres,season,
            age_limit,episode_total,trailer_id,trailer_type,voice,min_status,
            views,added_by,added_date,legacy_anime_id,active)
           SELECT 'anime',a.code,a.title,a.description,a.poster_id,a.genres,a.season,
                  a.age_limit,a.episode_total,a.trailer_id,a.trailer_type,a.voice,
                  a.min_status,a.views,a.added_by,a.added_date,a.id,1
           FROM anime a"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_item_categories(media_id, category_slug, sort_order)
           SELECT id, media_type, 0 FROM media_items"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_parts
           (media_id,part_type,season_number,part_number,title,file_id,file_type,
            added_by,added_date,active)
           SELECT m.id,
                  CASE WHEN e.ep_type='ova' THEN 'ova' ELSE 'episode' END,
                  1,e.ep_num,NULL,e.file_id,e.file_type,NULL,e.added_date,1
             FROM episodes e
             JOIN media_items m ON m.code=e.anime_code AND m.media_type='anime'"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_favorites(user_id,media_id,added_at)
           SELECT f.user_id,m.id,f.added_at
             FROM favorites f JOIN media_items m
               ON m.code=f.anime_code AND m.media_type='anime'"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_watch_progress
           (user_id,media_id,part_type,season_number,part_number,watched_at)
           SELECT p.user_id,m.id,
                  CASE WHEN p.ep_type='ova' THEN 'ova' ELSE 'episode' END,
                  1,p.ep_num,p.watched_at
             FROM watch_progress p JOIN media_items m
               ON m.code=p.anime_code AND m.media_type='anime'"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_watch_history
           (user_id,media_id,part_type,season_number,part_number,watched_at)
           SELECT h.user_id,m.id,
                  CASE WHEN h.ep_type='ova' THEN 'ova' ELSE 'episode' END,
                  1,h.ep_num,h.watched_at
             FROM watch_history h JOIN media_items m
               ON m.code=h.anime_code AND m.media_type='anime'"""
    )
    c.execute(
        """INSERT OR IGNORE INTO media_notifications(user_id,media_id,enabled,added_at)
           SELECT n.user_id,m.id,n.enabled,n.added_at
             FROM anime_notifications n JOIN media_items m
               ON m.code=n.anime_code AND m.media_type='anime'"""
    )
    con.commit()
    con.close()
    logger.info("✅ Database tayyor")


# ============================================================
#  BOT
# ============================================================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
BOT_USERNAME = ""

# ============================================================
#  BACKUP MA'LUMOTLARI
# ============================================================
LAST_BACKUP_INFO: dict = {}

# ============================================================
#  USER HELPERS
# ============================================================

def reg_user(uid, uname, fname, referred_by=None):
    con = db()
    c = con.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    if c.fetchone():
        c.execute(
            "UPDATE users SET username=?,full_name=?,last_active=? WHERE user_id=?",
            (uname, fname, now, uid),
        )
        con.commit(); con.close()
        return False

    ref = f"r{uid}"
    ref_ok = False
    if referred_by and referred_by != uid:
        c.execute("SELECT user_id FROM users WHERE user_id=?", (referred_by,))
        if c.fetchone():
            c.execute("UPDATE users SET coins=coins+5 WHERE user_id=?", (referred_by,))
            ref_ok = True
        else:
            referred_by = None

    c.execute(
        "INSERT INTO users(user_id,username,full_name,ref_code,referred_by,join_date,last_active)"
        " VALUES(?,?,?,?,?,?,?)",
        (uid, uname, fname, ref, referred_by, now, now),
    )
    con.commit(); con.close()

    if ref_ok:
        try:
            bot.send_message(
                referred_by,
                "🎁 *Yangi referal!*\nDo'stingiz botga qo'shildi — +5 tanga! 💰",
            )
        except Exception:
            pass
    return True


def get_user(uid):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    row = c.fetchone(); con.close()
    return dict(row) if row else None


def get_status(uid):
    if uid == OWNER_ID:
        return "owner"
    if is_admin(uid):
        return "admin"
    u = get_user(uid)
    if not u:
        return "user"
    now = local_now()
    if u["premium_expires"]:
        if now > datetime.strptime(u["premium_expires"], "%Y-%m-%d %H:%M:%S"):
            _expire(uid, "premium")
        else:
            return "premium"
    u = get_user(uid)
    if not u:
        return "user"
    if u["vip_expires"]:
        if now > datetime.strptime(u["vip_expires"], "%Y-%m-%d %H:%M:%S"):
            _expire(uid, "vip")
            return "user"
        else:
            return "vip"
    return u.get("status", "user")


def _expire(uid, kind):
    con = db(); c = con.cursor()
    if kind == "vip":
        c.execute("UPDATE users SET status='user',vip_expires=NULL WHERE user_id=?", (uid,))
        msg = "⚠️ *VIP muddatingiz tugadi.* Oddiy status qaytarildi.\n\nVIP olish: @nowloss"
    else:
        c.execute("UPDATE users SET status='user',premium_expires=NULL WHERE user_id=?", (uid,))
        msg = "⚠️ *Premium muddatingiz tugadi.* Oddiy status qaytarildi.\n\nPremium olish: @nowloss"
    con.commit(); con.close()
    try: bot.send_message(uid, msg)
    except Exception: pass


def add_coins(uid, n):
    con = db(); c = con.cursor()
    c.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (n, uid))
    c.execute("SELECT coins,status,vip_expires,premium_expires FROM users WHERE user_id=?", (uid,))
    row = c.fetchone(); con.commit(); con.close()
    if row and row["coins"] >= 50:
        if row["status"] == "user" and not row["vip_expires"] and not row["premium_expires"]:
            _give_vip(uid, auto=True)


def _give_vip(uid, auto=False):
    exp = (local_now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    con = db(); c = con.cursor()
    try:
        if auto:
            c.execute(
                """
                UPDATE users
                   SET status='vip', vip_expires=?, coins=coins-50
                 WHERE user_id=?
                   AND coins >= 50
                   AND status='user'
                   AND vip_expires IS NULL
                   AND premium_expires IS NULL
                """,
                (exp, uid),
            )
        else:
            c.execute(
                "UPDATE users SET status='vip', vip_expires=? WHERE user_id=?",
                (exp, uid),
            )
        if c.rowcount != 1:
            con.rollback()
            return False
        con.commit()
    except Exception as e:
        con.rollback()
        logger.error(f"VIP berish xatosi: {e}")
        return False
    finally:
        con.close()

    try:
        if auto:
            u2 = get_user(uid)
            new_balance = u2["coins"] if u2 else 0
            bot.send_message(
                uid,
                f"⭐ *VIP status berildi!*\n\n"
                f"50 tanga to'pladingiz — avtomatik VIP!\n"
                f"Muddat: 30 kun 🎉\n\n"
                f"💰 Balansdan 50 🪙 yechildi.\n"
                f"🪙 Qolgan balans: *{new_balance}* tanga",
            )
        else:
            bot.send_message(uid, "⭐ *VIP status berildi!*\n\nMuddat: 30 kun 🎉")
    except Exception:
        pass
    return True


def give_premium(uid):
    exp = (local_now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    con = db(); c = con.cursor()
    c.execute("UPDATE users SET status='premium',premium_expires=? WHERE user_id=?", (exp, uid))
    con.commit(); con.close()


def all_user_ids():
    con = db(); c = con.cursor()
    c.execute("SELECT user_id FROM users WHERE blocked=0")
    ids = [r["user_id"] for r in c.fetchall()]; con.close()
    return ids


def get_stats():
    con = db(); c = con.cursor()
    today = local_today().strftime("%Y-%m-%d")
    def q(sql, *a):
        c.execute(sql, a); return c.fetchone()[0]
    c.execute(
        "SELECT media_type, COUNT(*) AS count "
        "FROM media_items WHERE active=1 GROUP BY media_type"
    )
    media_counts = {
        row["media_type"]: row["count"]
        for row in c.fetchall()
    }
    s = {
        "total":   q("SELECT COUNT(*) FROM users"),
        "today":   q("SELECT COUNT(*) FROM users WHERE join_date LIKE ?", f"{today}%"),
        "active":  q("SELECT COUNT(*) FROM users WHERE last_active LIKE ?", f"{today}%"),
        "vip":     q("SELECT COUNT(*) FROM users WHERE status='vip'"),
        "premium": q("SELECT COUNT(*) FROM users WHERE status='premium'"),
        "blocked": q("SELECT COUNT(*) FROM users WHERE blocked=1"),
        "media_total": q("SELECT COUNT(*) FROM media_items WHERE active=1"),
        "media_counts": media_counts,
        "parts": q("SELECT COUNT(*) FROM media_parts WHERE active=1"),
    }
    con.close(); return s


# ============================================================
#  ADMIN HELPERS
# ============================================================

def is_admin(uid):
    if uid == OWNER_ID: return True
    con = db(); c = con.cursor()
    c.execute("SELECT 1 FROM admins WHERE user_id=?", (uid,))
    r = c.fetchone(); con.close()
    return r is not None


def add_admin(uid, by):
    con = db(); c = con.cursor()
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("INSERT INTO admins(user_id,added_by,added_date) VALUES(?,?,?)", (uid, by, now))
        # Yangi admin uchun bo'sh ruxsatlar yozuvi qo'sh
        c.execute(
            "INSERT OR IGNORE INTO admin_permissions(user_id) VALUES(?)", (uid,)
        )
        con.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def admin_has_any_manual_perm(uid):
    """Admin uchun qo'lda post ruxsatlaridan birortasi bor-yo'qligini tekshiradi."""
    if uid == OWNER_ID:
        return True
    for perm in ("manual_post", "manual_post_history", "manual_post_edit", "manual_post_delete", "manual_post_repost"):
        if admin_has_perm(uid, perm):
            return True
    return False


def remove_admin(uid):
    if uid == OWNER_ID: return False
    con = db(); c = con.cursor()
    c.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    removed = c.rowcount
    c.execute("DELETE FROM admin_permissions WHERE user_id=?", (uid,))
    con.commit(); con.close()
    return removed > 0


def list_admins():
    con = db(); c = con.cursor()
    c.execute("SELECT user_id,added_date FROM admins")
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


# ============================================================
#  ADMIN RUXSATLARI HELPERS
# ============================================================

PERM_LIST = [
    ("add_media",           "➕ Media qo'shish"),
    ("add_ep",              "📁 Media qismlarini boshqarish"),
    ("edit_media",          "✏️ Media tahrirlash"),
    ("del_media",           "🗑️ Media o'chirish"),
    # Legacy permission aliases remain readable for old admin rows.
    ("add_anime",           "Legacy: anime qo'shish"),
    ("edit_anime",          "Legacy: anime tahrirlash"),
    ("del_anime",           "Legacy: anime o'chirish"),
    ("stats",               "📊 Statistika"),
    ("broadcast",           "📢 Xabar yuborish"),
    ("autopost",            "📡 Avtopost"),
    ("manual_post",         "✍️ Qo'lda post yaratish"),
    ("manual_post_history", "📋 Qo'lda postlar tarixi"),
    ("manual_post_edit",    "✏️ Qo'lda postni tahrirlash"),
    ("manual_post_delete",  "🗑️ Qo'lda postni o'chirish"),
    ("manual_post_repost",  "🔁 Qo'lda postni qayta joylash"),
    ("user_manage",         "👥 Foydalanuvchilarni boshqarish"),
]
VALID_PERMISSIONS = {key for key, _ in PERM_LIST}


def admin_media_perm(uid, action):
    """Universal admin actions with legacy permission compatibility."""
    aliases = {
        "add": ("add_media", "add_anime"),
        "parts": ("add_ep",),
        "edit": ("edit_media", "edit_anime"),
        "delete": ("del_media", "del_anime"),
    }
    return any(admin_has_perm(uid, key) for key in aliases.get(action, (action,)))


def admin_has_perm(uid, perm):
    """Admin uchun ruxsatni tekshiradi. Owner har doim True."""
    if perm not in VALID_PERMISSIONS:
        return False
    if uid == OWNER_ID:
        return True
    con = db(); c = con.cursor()
    c.execute(f"SELECT {perm} FROM admin_permissions WHERE user_id=?", (uid,))
    row = c.fetchone(); con.close()
    return bool(row and row[perm])


def get_admin_perms(uid):
    """Admin uchun barcha ruxsatlarni dict ko'rinishida qaytaradi."""
    if uid == OWNER_ID:
        return {k: 1 for k, _ in PERM_LIST}
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM admin_permissions WHERE user_id=?", (uid,))
    row = c.fetchone(); con.close()
    if row:
        return dict(row)
    return {k: 0 for k, _ in PERM_LIST}


def toggle_admin_perm(uid, perm):
    """Adminning ruxsatini yoqish/o'chirish."""
    if perm not in VALID_PERMISSIONS:
        return False
    con = db(); c = con.cursor()
    c.execute(
        "INSERT OR IGNORE INTO admin_permissions(user_id) VALUES(?)", (uid,)
    )
    c.execute(
        f"UPDATE admin_permissions SET {perm} = CASE WHEN {perm}=1 THEN 0 ELSE 1 END WHERE user_id=?",
        (uid,),
    )
    con.commit(); con.close()
    return True


# ============================================================
#  MAJBURIY OBUNA KANAL HELPERS
# ============================================================

PLATFORM_ICONS = {'telegram': '📢', 'instagram': '📸', 'youtube': '▶️'}


def get_channels(only_active=False, platform=None):
    con = db(); c = con.cursor()
    q = "SELECT * FROM channels WHERE 1=1"
    params = []
    if only_active:
        q += " AND active=1"
    if platform:
        q += " AND platform=?"
        params.append(platform)
    c.execute(q, params)
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def add_channel(cid, name, url, platform='telegram'):
    con = db(); c = con.cursor()
    try:
        c.execute("INSERT INTO channels VALUES(?,?,?,?,1)", (cid, name, url, platform))
        con.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def del_channel(cid):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM channels WHERE channel_id=?", (cid,))
    n = c.rowcount; con.commit(); con.close(); return n > 0


def toggle_channel(cid):
    con = db(); c = con.cursor()
    c.execute("UPDATE channels SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE channel_id=?", (cid,))
    con.commit(); con.close()


def check_sub(uid):
    st = get_status(uid)
    if st in ("premium", "owner", "admin"):
        return True
    chs = get_channels(only_active=True, platform='telegram')
    if not chs:
        return True
    for ch in chs:
        try:
            m = bot.get_chat_member(ch["channel_id"], uid)
            if m.status in ("left", "kicked"):
                return False
        except Exception as e:
            logger.warning(f"Kanal tekshirish [{ch['channel_id']}]: {e}")
    return True


def require_sub(uid, chat_id):
    active_chs = get_channels(only_active=True)
    if not active_chs or check_sub(uid):
        return True
    safe(bot.send_message, chat_id,
        "📢 *Botdan foydalanish uchun quyidagi sahifalarga obuna bo'ling:*\n\n"
        "Obuna bo'lgach ✅ *Tekshirish* tugmasini bosing.",
        reply_markup=sub_kb())
    return False


def require_sub_cb(call):
    uid = call.from_user.id
    chs = get_channels()
    if not chs or check_sub(uid):
        return True
    bot.answer_callback_query(call.id, "❌ Avval kanallarga obuna bo'ling!", show_alert=True)
    safe(bot.send_message, call.message.chat.id,
        "📢 *Botdan foydalanish uchun kanallarga obuna bo'ling:*\n\n"
        "Obuna bo'lgach ✅ *Tekshirish* tugmasini bosing.",
        reply_markup=sub_kb())
    return False


# ============================================================
#  AVTOPOST KANAL HELPERS
# ============================================================

def get_autopost_channels(only_active=False):
    con = db(); c = con.cursor()
    if only_active:
        c.execute("SELECT * FROM autopost_channels WHERE active=1")
    else:
        c.execute("SELECT * FROM autopost_channels")
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def add_autopost_channel(cid, name, url):
    con = db(); c = con.cursor()
    try:
        c.execute(
            "INSERT INTO autopost_channels(channel_id,channel_name,channel_url,active) VALUES(?,?,?,1)",
            (cid, name, url),
        )
        con.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def del_autopost_channel(cid):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM autopost_channels WHERE channel_id=?", (cid,))
    n = c.rowcount; con.commit(); con.close(); return n > 0


def toggle_autopost_channel(cid):
    """Avtopost kanalini yoqish/o'chirish."""
    con = db(); c = con.cursor()
    c.execute(
        "UPDATE autopost_channels SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE channel_id=?",
        (cid,),
    )
    con.commit()
    c.execute("SELECT active FROM autopost_channels WHERE channel_id=?", (cid,))
    row = c.fetchone(); con.close()
    return bool(row and row["active"])


def get_autopost_setting(key, default=""):
    con = db(); c = con.cursor()
    c.execute("SELECT value FROM autopost_settings WHERE key=?", (key,))
    row = c.fetchone(); con.close()
    return row["value"] if row else default


def set_autopost_setting(key, value):
    con = db(); c = con.cursor()
    c.execute(
        "INSERT OR REPLACE INTO autopost_settings(key,value) VALUES(?,?)",
        (key, value),
    )
    con.commit(); con.close()


def get_main_channel_tag():
    """Postlar ichidagi asosiy kanal qatorini Owner sozlamasidan oladi."""
    try:
        value = get_autopost_setting("main_channel_tag", DEFAULT_CHANNEL_TAG).strip()
    except sqlite3.Error:
        value = DEFAULT_CHANNEL_TAG
    if not value or value == "-":
        value = DEFAULT_CHANNEL_TAG
    if value.startswith("📡"):
        value = value[1:].strip()
    if value.lower().startswith("kanal:"):
        value = value.split(":", 1)[1].strip()
    value = value.lstrip("@").strip()
    return f"@{value}" if value and value != "-" else DEFAULT_CHANNEL_TAG


def ensure_channel_tag(text):
    """Post matniga kanal qatorini aynan bir marta, eng pastga qo'shadi."""
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    forbidden_exact = {"none", "null", "skip", "kiritilmagan"}
    forbidden_prefixes = (
        "📝", "🎭", "🔎", "🎯 daraja:", "⭐ daraja:", "💎 daraja:",
    )
    filtered = []
    for line in lines:
        stripped = line.strip()
        lowered = stripped.lower().replace("’", "'").replace("ʻ", "'")
        if not stripped or stripped.startswith("📡"):
            continue
        if lowered in forbidden_exact or any(lowered.startswith(prefix) for prefix in forbidden_prefixes):
            continue
        if re.search(r"\b(?:none|skip|kiritilmagan)\b", lowered):
            continue
        if lowered.startswith("🎙️") and any(
            word in lowered for word in ("noma'lum", "nomalum", "unknown")
        ):
            continue
        filtered.append(line.rstrip())
    clean_text = "\n".join(filtered).strip()
    channel_line = f"📡 {get_main_channel_tag()}"
    return f"{clean_text}\n\n{channel_line}".strip() if clean_text else channel_line


def _history_user_name(uid):
    if uid == OWNER_ID:
        return "Owner"
    u = get_user(uid)
    if not u:
        return str(uid)
    return f"@{u['username']}" if u.get("username") else (u.get("full_name") or str(uid))


def _history_add(draft, channel, uid, status, error=None, message_id=None):
    """Har bir kanal uchun mustaqil avtopost natijasini saqlaydi."""
    con = db(); c = con.cursor()
    c.execute(
        """INSERT INTO autopost_history
        (anime_code,anime_title,post_type,season,ep_num,ep_type,channel_id,
         channel_name,channel_url,posted_by,posted_by_name,posted_at,status,error,
         message_id,text,media_id,media_type,button_text,genres,voice,min_status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            draft.get("anime_code"), draft.get("anime_title"), draft.get("post_type"),
            draft.get("season"), draft.get("ep_num"), draft.get("ep_type"),
            channel.get("channel_id"), channel.get("channel_name"), channel.get("channel_url"),
            uid, _history_user_name(uid), local_now().strftime("%Y-%m-%d %H:%M:%S"),
            status, error, message_id, draft.get("text"), draft.get("media_id"), draft.get("media_type"),
            draft.get("button_text"), draft.get("genres"), draft.get("voice"),
            draft.get("min_status"),
        ),
    )
    con.commit(); con.close()


def get_autopost_history(limit=20, offset=0, uid=None):
    con = db(); c = con.cursor()
    if uid is None or uid == OWNER_ID:
        c.execute(
            "SELECT * FROM autopost_history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    else:
        c.execute(
            "SELECT * FROM autopost_history WHERE posted_by=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (uid, limit, offset),
        )
    rows = [dict(r) for r in c.fetchall()]; con.close(); return rows


def get_history_item(history_id):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM autopost_history WHERE id=?", (history_id,))
    row = c.fetchone(); con.close()
    return dict(row) if row else None


def delete_history_item(history_id):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM autopost_history WHERE id=?", (history_id,))
    ok = c.rowcount > 0
    con.commit(); con.close(); return ok


def _friendly_post_error(exc):
    return (
        "Bot kanalga post yubora olmadi. Botning admin ekanini va "
        "post joylash ruxsati borligini tekshiring."
    )


# ============================================================
#  AVTOPOST POST YARATISH FUNKSIYALARI
# ============================================================

def _post_field(value):
    """Kanal postida ko'rinishi mumkin bo'lmagan bo'sh qiymatlarni tozalaydi."""
    if value is None:
        return ""
    value = str(value).strip()
    if value.lower() in {
        "", "none", "null", "skip", "kiritilmagan", "noma'lum", "nomalum",
        "unknown", "yo'q", "yoq",
    }:
        return ""
    return value


def _format_season(value):
    value = _post_field(value)
    if not value:
        return ""
    if value.lower() == "ova":
        return "OVA"
    value = re.sub(r"-?\s*fasl$", "", value, flags=re.IGNORECASE).strip()
    return f"{value}-fasl" if value else ""


def _format_episode(value):
    value = _post_field(value)
    if not value:
        return ""
    value = re.sub(r"-?\s*qism$", "", value, flags=re.IGNORECASE).strip()
    if value in {"0", "0.0"}:
        return ""
    return f"{value}-qism" if value else ""


def build_anime_post(anime_code):
    """Yangi anime uchun post matnini yaratadi."""
    a = get_anime(anime_code)
    if not a:
        return None, None
    lines = [f"⛩️ {a['title']}"]
    season = _post_field(a.get("season"))
    episode_total = ep_count(anime_code, "season")
    if season and episode_total:
        lines.append(f"📽️ {_format_season(season)} | 🎞️ {_format_episode(episode_total)}")
    elif season:
        lines.append(f"📽️ {_format_season(season)}")
    elif episode_total:
        lines.append(f"🎞️ {_format_episode(episode_total)}")
    voice = _post_field(a.get("voice"))
    if voice:
        lines.append(f"🎙️ {voice}")
    lines.append("✨ Anime joylandi!")
    txt = ensure_channel_tag("\n".join(lines))
    return txt, a.get("poster_id")


def build_episode_post(anime_code, ep_num=None, ep_type="season"):
    """Yangi qism uchun qisqacha post matnini yaratadi."""
    a = get_anime(anime_code)
    if not a:
        return None
    if ep_num is None:
        ep_num = ep_count(anime_code, ep_type)
    tur = "OVA" if ep_type == "ova" else _format_season(a.get("season"))
    lines = [f"⛩️ {a['title']}"]
    episode_label = _format_episode(ep_num)
    meta = []
    if tur:
        meta.append(f"📺 {tur}")
    if episode_label:
        meta.append(f"🎞️ {episode_label}")
    if meta:
        lines.append(" | ".join(meta))
    lines.append("✨ Yangi qism joylandi!")
    voice = _post_field(a.get("voice"))
    if voice:
        lines.append(f"🎙️ {voice}")
    txt = ensure_channel_tag("\n".join(lines))
    return txt


def build_media_post(media_code, part_number=None, part_type="part", season_number=None):
    """Universal katalogdagi media uchun avtopost matnini yaratadi."""
    media = get_media_item(media_code)
    if not media:
        return None
    if media.get("media_type") == "anime":
        if part_number is not None:
            legacy_type = "ova" if part_type == "ova" else "season"
            return build_episode_post(media_code, part_number, legacy_type)
        text, _ = build_anime_post(media_code)
        return text

    title = media.get("title") or media_code
    lines = [f"{media_type_icon(media.get('media_type'))} {title}"]
    season = season_number or media.get("season")
    if season:
        lines.append(f"📺 {_format_season(season)}")
    if part_number is not None:
        lines.append(
            f"📁 {media_part_label(part_type)}: {_format_episode(part_number)}"
        )
    voice = _post_field(media.get("voice"))
    if voice:
        lines.append(f"🎙️ {voice}")
    lines.append(
        "✨ Yangi bo'lim joylandi!" if part_number is not None
        else "✨ Media joylandi!"
    )
    return ensure_channel_tag("\n".join(lines))


def _replace_post_genres(text, genres):
    """Janr bazada saqlanadi, lekin ixcham kanal postida ko'rsatilmaydi."""
    return ensure_channel_tag(text)


def get_watch_inline_kb(anime_code, button_text=None):
    """Legacy va universal media kodi uchun deep-link tugmasi yaratadi."""
    if not anime_code or not get_media_item(anime_code):
        return None
    btn_text = button_text or get_autopost_setting("watch_btn_text", "▶️ TOMOSHA QILISH")
    username = (BOT_USERNAME or os.environ.get("BOT_USERNAME", "anibestuzbbot")).lstrip("@")
    url = f"https://t.me/{username}?start={anime_code}"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(btn_text, url=url))
    return kb


def send_to_autopost_channels(text, poster_id=None, anime_code=None, channel_ids=None,
                               draft=None, posted_by=None, button_text=None,
                               media_type=None):
    """
    Avtopost kanallariga xabar yuboradi.
    channel_ids=None bo'lsa barcha faol kanallarga yuboradi.
    """
    if channel_ids is None:
        channels = get_autopost_channels(only_active=True)
    else:
        channels = [
            c for c in get_autopost_channels(only_active=True)
            if c["channel_id"] in channel_ids
        ]

    if not channels:
        return 0, 0
    media = get_media_item(anime_code) if anime_code else None
    if not media:
        logger.error("Avtopost bekor qilindi: media kodi bazada topilmadi [%s]", anime_code)
        return 0, len(channels)
    if draft and draft.get("post_type") == "new_episode":
        # Yangi qism kanalga fayl bilan emas, katalog posterining o'zi bilan chiqadi.
        poster_id = media.get("poster_id")
        media_type = "photo" if poster_id else None

    text = ensure_channel_tag(text)
    history_draft = None
    if draft is not None:
        history_draft = dict(draft)
        history_draft["text"] = text
        if draft.get("post_type") == "new_episode":
            history_draft["media_id"] = poster_id
            history_draft["media_type"] = media_type
    kb = get_watch_inline_kb(anime_code, button_text) if anime_code else None
    ok = 0; fail = 0
    for ch in channels:
        try:
            actual_media_type = media_type or ("photo" if poster_id else None)
            sent_message = None
            if poster_id and actual_media_type == "video":
                sent_message = bot.send_video(
                    ch["channel_id"], poster_id, caption=text,
                    reply_markup=kb, parse_mode=None
                )
            elif poster_id and actual_media_type == "animation":
                sent_message = bot.send_animation(
                    ch["channel_id"], poster_id, caption=text,
                    reply_markup=kb, parse_mode=None
                )
            elif poster_id and actual_media_type == "document":
                sent_message = bot.send_document(
                    ch["channel_id"], poster_id, caption=text,
                    reply_markup=kb, parse_mode=None
                )
            elif poster_id and actual_media_type == "audio":
                sent_message = bot.send_audio(
                    ch["channel_id"], poster_id, caption=text,
                    reply_markup=kb, parse_mode=None
                )
            elif poster_id and actual_media_type == "voice":
                sent_message = bot.send_voice(
                    ch["channel_id"], poster_id, caption=text,
                    reply_markup=kb, parse_mode=None
                )
            elif poster_id:
                sent_message = bot.send_photo(
                    ch["channel_id"], poster_id,
                    caption=text, reply_markup=kb, parse_mode=None
                )
            else:
                sent_message = bot.send_message(
                    ch["channel_id"], text,
                    reply_markup=kb, parse_mode=None
                )
            ok += 1
            if history_draft is not None:
                _history_add(
                    history_draft, ch, posted_by or OWNER_ID, "success",
                    message_id=getattr(sent_message, "message_id", None),
                )
        except Exception as e:
            logger.error(f"Avtopost kanal [{ch['channel_id']}]: {e}")
            fail += 1
            if history_draft is not None:
                _history_add(
                    history_draft, ch, posted_by or OWNER_ID,
                    "failed", _friendly_post_error(e),
                )
    return ok, fail


def _draft_from_state(uid):
    """Tayyorlanayotgan postning media katalogidan mustaqil nusxasini qaytaradi."""
    si = sget(uid)
    data = dict(si.get("data", {}))
    code = data.get("media_code") or data.get("anime_code") or data.get("code")
    if not code:
        return None
    media = get_media_item(code) or {}
    post_type = data.get("post_type")
    ep_type = data.get("ep_type")
    ep_num = data.get("ep_num")
    if post_type is None:
        post_type = {
            "ap_ep_wait": "new_episode",
            "ap_existing_wait": "new_anime",
        }.get(si.get("state"), "new_anime")
    repost_text = None
    if post_type == "repost":
        repost_text = data.get("text", "")
        post_type = data.get("source_post_type")
        if post_type not in {"new_anime", "new_episode"}:
            post_type = "new_anime"
    elif post_type == "existing_anime":
        post_type = "new_anime"
    if repost_text is not None:
        text = repost_text
    elif post_type == "new_episode":
        text = build_media_post(
            code,
            ep_num,
            ep_type or "part",
            data.get("season_number") or data.get("season"),
        )
    else:
        text = build_media_post(code)
    if not text:
        return None
    draft = {
        "anime_code": code,
        "media_code": code,
        "media_catalog_type": media.get("media_type"),
        "anime_title": data.get("anime_title") or media.get("title") or code,
        "post_type": post_type,
        "season": data.get("season") or media.get("season"),
        "season_number": data.get("season_number"),
        "ep_num": ep_num,
        "ep_type": ep_type,
        "text": data.get("text") or text,
        "media_id": data.get("media_id"),
        "media_type": data.get("media_type"),
        "button_text": data.get("button_text") or get_autopost_setting(
            "watch_btn_text", "▶️ TOMOSHA QILISH"
        ),
        "genres": data.get("genres", media.get("genres")),
        "voice": data.get("voice", media.get("voice")),
        "min_status": data.get("min_status", media.get("min_status")),
    }
    if "media_id" not in data and post_type == "new_anime":
        draft["media_id"] = media.get("poster_id")
        draft["media_type"] = "photo" if media.get("poster_id") else None
    # Yangi bo'lim avtopostida bo'lim fayli emas, katalog posteri ishlatiladi.
    if post_type == "new_episode":
        draft["media_id"] = media.get("poster_id")
        draft["media_type"] = "photo" if media.get("poster_id") else None
    return draft


def _draft_from_history(row):
    source_type = row.get("post_type")
    post_type = source_type if source_type in {"new_anime", "new_episode"} else "new_anime"
    media = get_media_item(row.get("anime_code")) or {}
    draft = {
        "anime_code": row.get("anime_code"),
        "media_code": row.get("anime_code"),
        "media_catalog_type": media.get("media_type"),
        "anime_title": row.get("anime_title") or row.get("anime_code"),
        "post_type": post_type,
        "source_post_type": source_type,
        "season": row.get("season"),
        "season_number": row.get("season_number"),
        "ep_num": row.get("ep_num"),
        "ep_type": row.get("ep_type"),
        "text": row.get("text") or "",
        "media_id": row.get("media_id"),
        "media_type": row.get("media_type"),
        "button_text": row.get("button_text") or get_autopost_setting(
            "watch_btn_text", "▶️ TOMOSHA QILISH"
        ),
        "genres": row.get("genres"),
        "voice": row.get("voice"),
        "min_status": row.get("min_status"),
    }
    if post_type == "new_episode":
        draft["media_id"] = media.get("poster_id")
        draft["media_type"] = "photo" if media.get("poster_id") else None
    return draft


def _draft_store(uid, draft):
    si = sget(uid)
    data = dict(si.get("data", {}))
    for key in ("anime_code", "anime_title", "post_type", "source_post_type",
                "season", "ep_num", "ep_type", "text", "media_id", "media_type",
                "button_text", "genres", "voice", "min_status", "custom_text",
                "media_code", "media_catalog_type", "season_number",
                "edit_return_state"):
        if key in draft:
            data[key] = draft[key]
    sset(uid, si.get("state", "ap_anime_wait"), data)


def _draft_keyboard(uid, ready=True):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Matnni tahrirlash", callback_data="APE_TEXT"),
        types.InlineKeyboardButton("🏷️ Tasnifni tahrirlash", callback_data="APE_GENRES"),
        types.InlineKeyboardButton("🖼️ Rasmni almashtirish", callback_data="APE_PHOTO"),
        types.InlineKeyboardButton("🎬 Videoni almashtirish", callback_data="APE_VIDEO"),
        types.InlineKeyboardButton("🗑️ Medianı olib tashlash", callback_data="APE_MEDIA_CLEAR"),
        types.InlineKeyboardButton("🔘 Tugma matnini tahrirlash", callback_data="APE_BUTTON"),
        types.InlineKeyboardButton("👀 Preview", callback_data="APE_PREVIEW"),
    )
    if ready:
        kb.add(types.InlineKeyboardButton("✅ Tayyor", callback_data="APE_DONE"))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="AP_CANCEL"))
    return kb


def _draft_preview(chat_id, draft, prefix="👀 *Preview (kanalga yuborilmaydi):*"):
    draft = dict(draft or {})
    if draft.get("post_type") == "new_episode":
        media = get_media_item(draft.get("media_code") or draft.get("anime_code")) or {}
        draft["media_id"] = media.get("poster_id")
        draft["media_type"] = "photo" if media.get("poster_id") else None
    draft["text"] = ensure_channel_tag(draft.get("text", ""))
    kb = get_watch_inline_kb(
        draft.get("media_code") or draft.get("anime_code"),
        draft.get("button_text"),
    )
    safe(bot.send_message, chat_id, prefix)
    media_id = draft.get("media_id")
    media_type = draft.get("media_type")
    if media_id and media_type == "video":
        safe(bot.send_video, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    elif media_id and media_type == "animation":
        safe(bot.send_animation, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    elif media_id and media_type == "document":
        safe(bot.send_document, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    elif media_id and media_type == "audio":
        safe(bot.send_audio, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    elif media_id and media_type == "voice":
        safe(bot.send_voice, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    elif media_id:
        safe(bot.send_photo, chat_id, media_id, caption=draft["text"], reply_markup=kb, parse_mode=None)
    else:
        safe(bot.send_message, chat_id, draft["text"], reply_markup=kb, parse_mode=None)


def _history_post_type_label(post_type):
    return {
        "new_anime": "🆕 Yangi anime",
        "new_episode": "📺 Yangi qism",
        "existing_anime": "🆕 Yangi anime",
        "repost": "🆕 Yangi anime",
    }.get(post_type, "🆕 Yangi anime")


def _history_keyboard(history_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("👀 Postni ko'rish", callback_data=f"APH_VIEW_{history_id}"),
        types.InlineKeyboardButton("🔁 Qayta joylash", callback_data=f"APH_REPOST_{history_id}"),
        types.InlineKeyboardButton("🗑️ Tarixdan o'chirish", callback_data=f"APH_DELETE_{history_id}"),
        types.InlineKeyboardButton("⬅️ Orqaga", callback_data="APS_HISTORY"),
    )
    return kb


def _history_menu_keyboard():
    return _history_menu_keyboard_for(None)


def _history_menu_keyboard_for(uid):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in get_autopost_history(20, uid=None if uid in (None, OWNER_ID) else uid):
        status = "✅" if row["status"] == "success" else "❌"
        title = (row.get("anime_title") or row.get("anime_code") or "Anime")[:35]
        kb.add(types.InlineKeyboardButton(
            f"{status} {title} · {row.get('channel_name') or row.get('channel_id')}",
            callback_data=f"APH_DETAIL_{row['id']}",
        ))
    kb.add(types.InlineKeyboardButton("🔙 Avtopost sozlamalari", callback_data="SET_AUTOPOST"))
    return kb


def _can_use_autopost(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "autopost"))


def _send_draft(uid, draft, channel_ids=None):
    channels = get_autopost_channels(only_active=True)
    if channel_ids is not None:
        channels = [c for c in channels if c["channel_id"] in channel_ids]
    if not channels:
        return 0, 0
    return send_to_autopost_channels(
        draft.get("text", ""),
        draft.get("media_id"),
        draft.get("media_code") or draft.get("anime_code"),
        [c["channel_id"] for c in channels],
        draft=draft,
        posted_by=uid,
        button_text=draft.get("button_text"),
        media_type=draft.get("media_type"),
    )


# ============================================================
#  ANIME HELPERS
# ============================================================

MEDIA_TYPE_NAMES = {
    "anime": "Anime",
    "movie": "Film",
    "tv_series": "Serial",
    "k_drama": "Koreys dramasi",
    "cartoon": "Multfilm",
    "other": "Boshqa media",
}
MEDIA_TYPE_ICONS = {
    "anime": "🎬",
    "movie": "🎥",
    "tv_series": "📺",
    "k_drama": "🇰🇷",
    "cartoon": "🧸",
    "other": "📚",
}
MEDIA_TYPES = tuple(MEDIA_TYPE_NAMES)
MEDIA_CATEGORY_DEFAULTS = (
    ("anime", "Anime", "🎬", 10),
    ("movie", "Filmlar", "🎥", 20),
    ("tv_series", "Seriallar", "📺", 30),
    ("k_drama", "Koreys dramalari", "🇰🇷", 40),
    ("cartoon", "Multfilmlar", "🧸", 50),
    ("other", "Boshqa media", "📚", 60),
)


def seed_media_categories(cursor):
    """Standart media kategoriyalarini mavjud custom yozuvlarni saqlagan holda qo'shadi."""
    for slug, title, icon, sort_order in MEDIA_CATEGORY_DEFAULTS:
        cursor.execute(
            "INSERT OR IGNORE INTO media_categories(slug,title,icon,sort_order,active) "
            "VALUES(?,?,?,?,1)",
            (slug, title, icon, sort_order),
        )


def get_media_categories(only_active=True):
    con = db()
    c = con.cursor()
    sql = "SELECT * FROM media_categories"
    if only_active:
        sql += " WHERE active=1"
    sql += " ORDER BY sort_order, title"
    c.execute(sql)
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def get_media_category(slug):
    con = db()
    c = con.cursor()
    c.execute("SELECT * FROM media_categories WHERE slug=?", (slug,))
    row = c.fetchone()
    con.close()
    return dict(row) if row else None


def get_media_item(code):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT * FROM media_items WHERE lower(code)=lower(?) AND active=1",
        (code,),
    )
    row = c.fetchone()
    con.close()
    return dict(row) if row else None


def get_media(code):
    """Universal katalog uchun public helper; legacy anime ham shu katalogda ko'rinadi."""
    return get_media_item(code)


def next_content_code(cursor=None):
    """Anime va universal media uchun global keyingi raqamli kodni qaytaradi."""
    owns_cursor = cursor is None
    con = db() if owns_cursor else None
    c = con.cursor() if owns_cursor else cursor
    try:
        used = set()
        for table in ("anime", "media_items"):
            c.execute(f"SELECT code FROM {table}")
            for row in c.fetchall():
                value = str(row[0] or "").strip()
                if value.isdigit():
                    used.add(int(value))
        return str(max(used, default=0) + 1)
    finally:
        if owns_cursor:
            con.close()


def get_media_item_by_id(media_id):
    con = db()
    c = con.cursor()
    c.execute("SELECT * FROM media_items WHERE id=? AND active=1", (media_id,))
    row = c.fetchone()
    con.close()
    return dict(row) if row else None


def media_type_label(media_type):
    return MEDIA_TYPE_NAMES.get(media_type, "Media")


def media_type_icon(media_type):
    return MEDIA_TYPE_ICONS.get(media_type, "🎬")


def media_part_label(part_type):
    return {
        "season": "Fasl",
        "episode": "Qism",
        "part": "Bo'lim",
        "movie": "Film fayli",
        "ova": "OVA/Special",
        "special": "Special",
    }.get(part_type, "Bo'lim")


def media_part_types(media):
    """Kontent turiga mos universal fayl bo'limlari."""
    if media and media.get("media_type") == "movie":
        return ("movie",)
    if media and media.get("media_type") == "anime":
        return ("episode", "ova", "special")
    return ("season", "episode", "part", "special")


def _media_category_for_type(media_type):
    return media_type if media_type in {slug for slug, *_ in MEDIA_CATEGORY_DEFAULTS} else "other"


def _sync_media_category(cursor, media_id, media_type, category_slug=None):
    slug = category_slug or _media_category_for_type(media_type)
    cursor.execute(
        "INSERT OR IGNORE INTO media_item_categories(media_id,category_slug,sort_order) "
        "VALUES(?,?,0)",
        (media_id, slug),
    )


def get_media_parts(media_id, part_type=None, season_number=None, active_only=True):
    where = ["media_id=?"]
    params = [int(media_id)]
    if active_only:
        where.append("active=1")
    if part_type and part_type != "all":
        where.append("part_type=?")
        params.append(part_type)
    if season_number not in (None, ""):
        where.append("season_number=?")
        params.append(int(season_number))
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT * FROM media_parts WHERE " + " AND ".join(where) +
        " ORDER BY season_number, part_type, part_number, id",
        params,
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def next_media_part_number(media_id, part_type="part", season_number=1):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT COALESCE(MAX(part_number),0)+1 FROM media_parts "
        "WHERE media_id=? AND part_type=? AND season_number=?",
        (int(media_id), part_type, int(season_number or 1)),
    )
    number = int(c.fetchone()[0] or 1)
    con.close()
    return number


def add_media_part(media_id, part_type, file_id, file_type="document",
                   season_number=1, part_number=None, title=None, added_by=None):
    part_type = str(part_type or "part").strip().lower()
    if part_type not in {"season", "episode", "part", "movie", "ova", "special"}:
        return False, None
    try:
        season_number = max(1, int(season_number or 1))
    except (TypeError, ValueError):
        return False, None
    if part_number in (None, ""):
        part_number = next_media_part_number(media_id, part_type, season_number)
    try:
        part_number = max(1, int(part_number))
    except (TypeError, ValueError):
        return False, None
    if not file_id:
        return False, None
    con = db()
    c = con.cursor()
    try:
        c.execute(
            """INSERT INTO media_parts
               (media_id,part_type,season_number,part_number,title,file_id,file_type,
                added_by,added_date,active)
               VALUES(?,?,?,?,?,?,?,?,?,1)""",
            (
                int(media_id), part_type, season_number, part_number, title,
                file_id, file_type or "document", added_by,
                local_now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        part_id = c.lastrowid
        con.commit()
        return True, part_id
    except sqlite3.IntegrityError:
        con.rollback()
        return False, None
    finally:
        con.close()


def get_media_part(part_id):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT p.*,m.title,m.code,m.media_type FROM media_parts p "
        "JOIN media_items m ON m.id=p.media_id "
        "WHERE p.id=? AND p.active=1",
        (int(part_id),),
    )
    row = c.fetchone()
    con.close()
    return dict(row) if row else None


def delete_media_part(part_id):
    con = db()
    c = con.cursor()
    c.execute("UPDATE media_parts SET active=0 WHERE id=? AND active=1", (int(part_id),))
    changed = c.rowcount == 1
    con.commit()
    con.close()
    return changed


def is_media_favorite(uid, media_id):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT 1 FROM media_favorites WHERE user_id=? AND media_id=?",
        (uid, int(media_id)),
    )
    result = c.fetchone() is not None
    con.close()
    return result


def toggle_media_favorite(uid, media_id):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT 1 FROM media_favorites WHERE user_id=? AND media_id=?",
        (uid, int(media_id)),
    )
    if c.fetchone():
        c.execute(
            "DELETE FROM media_favorites WHERE user_id=? AND media_id=?",
            (uid, int(media_id)),
        )
        enabled = False
    else:
        c.execute(
            "INSERT OR IGNORE INTO media_favorites(user_id,media_id,added_at) VALUES(?,?,?)",
            (uid, int(media_id), local_now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        enabled = True
    con.commit()
    con.close()
    return enabled


def media_notifications_enabled(uid, media_id):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT enabled FROM media_notifications WHERE user_id=? AND media_id=?",
        (uid, int(media_id)),
    )
    row = c.fetchone()
    con.close()
    return bool(row and row["enabled"])


def toggle_media_notification(uid, media_id):
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT enabled FROM media_notifications WHERE user_id=? AND media_id=?",
        (uid, int(media_id)),
    )
    row = c.fetchone()
    enabled = not bool(row["enabled"]) if row else True
    c.execute(
        """INSERT INTO media_notifications(user_id,media_id,enabled,added_at)
           VALUES(?,?,?,?)
           ON CONFLICT(user_id,media_id) DO UPDATE SET enabled=excluded.enabled""",
        (uid, int(media_id), int(enabled), local_now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    con.commit()
    con.close()
    return enabled


def record_media_watch(uid, media_id, part_number, part_type="part", season_number=1):
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    con = db()
    c = con.cursor()
    c.execute(
        """INSERT INTO media_watch_progress
           (user_id,media_id,part_type,season_number,part_number,watched_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id,media_id,part_type,season_number)
           DO UPDATE SET part_number=excluded.part_number,watched_at=excluded.watched_at""",
        (uid, int(media_id), part_type, int(season_number or 1), int(part_number), now),
    )
    c.execute(
        """INSERT INTO media_watch_history
           (user_id,media_id,part_type,season_number,part_number,watched_at)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(user_id,media_id,part_type,season_number,part_number)
           DO UPDATE SET watched_at=excluded.watched_at""",
        (uid, int(media_id), part_type, int(season_number or 1), int(part_number), now),
    )
    con.commit()
    con.close()
    return True


def get_media_watch_progress(uid, limit=10):
    con = db()
    c = con.cursor()
    c.execute(
        """SELECT p.*,m.title,m.code,m.media_type
           FROM media_watch_progress p JOIN media_items m ON m.id=p.media_id
          WHERE p.user_id=? AND m.active=1 ORDER BY p.watched_at DESC LIMIT ?""",
        (uid, int(limit)),
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def get_media_watch_history(uid, limit=20):
    con = db()
    c = con.cursor()
    c.execute(
        """SELECT h.*,m.title,m.code,m.media_type
           FROM media_watch_history h JOIN media_items m ON m.id=h.media_id
          WHERE h.user_id=? AND m.active=1 ORDER BY h.watched_at DESC LIMIT ?""",
        (uid, int(limit)),
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def list_media(media_type=None, query=None, page=0, per=10, category=None, genre=None):
    page = max(0, int(page))
    where = ["m.active=1"]
    params = []
    if media_type and media_type != "all":
        where.append("m.media_type=?")
        params.append(media_type)
    joins = []
    if category and category != "all":
        joins.append(
            "JOIN media_item_categories mic ON mic.media_id=m.id AND mic.category_slug=?"
        )
        params.append(category)
    if genre:
        where.append("lower(COALESCE(m.genres,'')) LIKE ?")
        params.append(f"%{normalize_search_text(genre)}%")
    if query:
        normalized = normalize_search_text(query)
        like = f"%{normalized}%"
        where.append(
            "(lower(m.title) LIKE ? OR lower(m.code) LIKE ? OR "
            "lower(COALESCE(m.genres,'')) LIKE ?)"
        )
        params.extend([like, like, like])
    clause = " AND ".join(where)
    con = db()
    c = con.cursor()
    c.execute(
        f"SELECT DISTINCT m.id,m.media_type,m.code,m.title,m.views FROM media_items m "
        f"{' '.join(joins)} "
        f"WHERE {clause} ORDER BY added_date DESC, id DESC LIMIT ? OFFSET ?",
        (*params, per, page * per),
    )
    rows = [dict(row) for row in c.fetchall()]
    c.execute(
        f"SELECT COUNT(DISTINCT m.id) FROM media_items m {' '.join(joins)} WHERE {clause}",
        params,
    )
    total = c.fetchone()[0]
    con.close()
    return rows, total


def search_media(query, limit=15, media_type=None, category=None, genre=None):
    needle = normalize_search_text(query)
    if not needle:
        return []
    rows, _ = list_media(
        media_type=media_type, query=None, page=0, per=10000,
        category=category, genre=genre,
    )
    con = db()
    c = con.cursor()
    ids = [row["id"] for row in rows]
    if not ids:
        con.close()
        return []
    placeholders = ",".join("?" for _ in ids)
    c.execute(
        f"SELECT * FROM media_items WHERE active=1 AND id IN ({placeholders}) "
        "ORDER BY added_date DESC, id DESC",
        ids,
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    exact_code, exact_title, partial = [], [], []
    for row in rows:
        code = normalize_search_text(row.get("code"))
        title = normalize_search_text(row.get("title"))
        genres = normalize_search_text(row.get("genres"))
        if code == needle:
            exact_code.append(row)
        elif title == needle:
            exact_title.append(row)
        elif needle in code or needle in title or needle in genres:
            partial.append(row)
    return (exact_code + exact_title + partial)[:limit]


def inc_media_views(media_id):
    con = db()
    c = con.cursor()
    c.execute(
        "UPDATE media_items SET views=COALESCE(views,0)+1 WHERE id=? AND active=1",
        (media_id,),
    )
    changed = c.rowcount == 1
    if changed:
        # Anime mirror views remain compatible with old statistics/backup tools.
        c.execute(
            """UPDATE anime SET views=COALESCE(views,0)+1
               WHERE code=(SELECT code FROM media_items WHERE id=? AND media_type='anime')""",
            (media_id,),
        )
    con.commit()
    con.close()
    return changed


def _mirror_anime_row(cursor, code):
    """Legacy anime yozuvini universal katalog bilan bir xil saqlaydi."""
    cursor.execute("SELECT * FROM anime WHERE code=?", (code,))
    anime = cursor.fetchone()
    if not anime:
        return
    cursor.execute(
        """INSERT INTO media_items
           (media_type,code,title,description,poster_id,genres,season,
            age_limit,episode_total,trailer_id,trailer_type,voice,min_status,
            views,added_by,added_date,legacy_anime_id,active)
           VALUES('anime',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
           ON CONFLICT(code) DO UPDATE SET
             media_type='anime', title=excluded.title, description=excluded.description,
             poster_id=excluded.poster_id, genres=excluded.genres, season=excluded.season,
             age_limit=excluded.age_limit, episode_total=excluded.episode_total,
             trailer_id=excluded.trailer_id, trailer_type=excluded.trailer_type,
             voice=excluded.voice, min_status=excluded.min_status, views=excluded.views,
             added_by=excluded.added_by, added_date=excluded.added_date,
             legacy_anime_id=excluded.legacy_anime_id, active=1""",
        (
            anime["code"], anime["title"], anime["description"], anime["poster_id"],
            anime["genres"], anime["season"], anime["age_limit"],
            anime["episode_total"], anime["trailer_id"], anime["trailer_type"],
            anime["voice"], anime["min_status"], anime["views"], anime["added_by"],
            anime["added_date"], anime["id"],
        ),
    )
    cursor.execute(
        "SELECT id FROM media_items WHERE code=? AND media_type='anime'",
        (anime["code"],),
    )
    mirrored = cursor.fetchone()
    if mirrored:
        _sync_media_category(cursor, mirrored["id"], "anime")


def add_media_item(media_type, code, title, description=None, poster_id=None,
                   main_media_id=None, main_media_type=None, genres=None,
                   season=None, episode_total=None, age_limit=None,
                   trailer_id=None, trailer_type=None, voice=None,
                   min_status="user", added_by=None):
    if media_type not in MEDIA_TYPES:
        return False
    code = str(code or "").strip()
    title = str(title or "").strip()
    if not title or (code and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code)):
        return False
    if min_status not in ST_ORDER:
        return False
    if episode_total not in (None, ""):
        if not str(episode_total).isdigit() or int(episode_total) < 0:
            return False
        episode_total = str(int(episode_total))
    # Anime turi — legacy `anime` jadvali orqali yaratiladi (add_anime o'zi
    # media_items'ga ham mirrorlaydi), shu bilan tahrirlash/o'chirish keyinchalik
    # bir xil yozuv yo'lidan (upd_anime/del_anime) ishlashini kafolatlaydi.
    if media_type == "anime":
        return add_anime(
            code, title, description or "", poster_id, genres or "",
            season or "1", None, voice or "", min_status, added_by,
        )
    con = db()
    c = con.cursor()
    try:
        if not code:
            code = next_content_code(c)
        c.execute(
            "SELECT 1 FROM anime WHERE lower(code)=lower(?) "
            "UNION ALL SELECT 1 FROM media_items WHERE lower(code)=lower(?) LIMIT 1",
            (code, code),
        )
        if c.fetchone():
            return False
        c.execute(
            """INSERT INTO media_items
               (media_type,code,title,description,poster_id,main_media_id,
                main_media_type,genres,season,episode_total,age_limit,trailer_id,
                trailer_type,voice,min_status,views,added_by,added_date,active)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,1)""",
            (
                media_type, code, title, description, poster_id, main_media_id,
                main_media_type, genres, season, episode_total, age_limit,
                trailer_id, trailer_type, voice, min_status, added_by,
                local_now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        _sync_media_category(c, c.lastrowid, media_type)
        con.commit()
        return True
    except sqlite3.IntegrityError:
        con.rollback()
        return False
    finally:
        con.close()


def add_media(*args, **kwargs):
    """Universal media yozuvi qo'shish uchun qisqa public helper."""
    return add_media_item(*args, **kwargs)


def update_media(code, **updates):
    """Barcha kontent turlari uchun umumiy update adapteri.

    Anime qatorlari legacy jadvalda saqlanadi, qolgan turlar media_items
    jadvalida yangilanadi. Shu sababli eski deep-link va callbacklar buzilmaydi.
    """
    allowed = {
        "media_type", "title", "description", "poster_id", "main_media_id",
        "main_media_type", "genres", "season", "episode_total", "age_limit",
        "trailer_id", "trailer_type", "voice", "min_status", "active",
    }
    fields = {key: value for key, value in updates.items() if key in allowed}
    if not fields:
        return False
    if fields.get("media_type") not in (None, *MEDIA_TYPES):
        return False
    if fields.get("min_status") not in (None, *ST_ORDER):
        return False
    if "title" in fields and not str(fields["title"] or "").strip():
        return False
    if "episode_total" in fields and fields["episode_total"] not in (None, ""):
        if not str(fields["episode_total"]).isdigit() or int(fields["episode_total"]) < 0:
            return False
        fields["episode_total"] = str(int(fields["episode_total"]))
    current = get_media_item(code)
    if not current:
        return False
    if current.get("media_type") == "anime":
        if "media_type" in fields:
            return False
        legacy_fields = {
            key: value for key, value in fields.items()
            if key in {
                "title", "description", "poster_id", "genres", "season",
                "age_limit", "episode_total", "trailer_id", "trailer_type",
                "voice", "min_status",
            }
        }
        for field, value in legacy_fields.items():
            if not upd_anime(code, field, value):
                return False
        return bool(legacy_fields)
    con = db()
    c = con.cursor()
    try:
        assignments = ", ".join(f"{key}=?" for key in fields)
        values = list(fields.values()) + [code]
        c.execute(
            f"UPDATE media_items SET {assignments} "
            "WHERE lower(code)=lower(?) AND active=1",
            values,
        )
        changed = c.rowcount == 1
        if changed and "media_type" in fields:
            _sync_media_category(c, current["id"], fields["media_type"])
        con.commit()
        return changed
    except Exception:
        con.rollback()
        logger.exception("Universal media yangilanmadi [%s]", code)
        return False
    finally:
        con.close()


def delete_media(code):
    """Universal kontentni va unga bog'langan ma'lumotlarni butunlay o'chiradi."""
    current = get_media_item(code)
    if not current:
        return False
    if current.get("media_type") == "anime":
        return del_anime(code)
    con = db()
    c = con.cursor()
    try:
        media_id = current["id"]
        # This action is a real delete, not a soft-delete/archive. Remove
        # dependent rows first so old favorites, history, and notifications
        # cannot keep pointing at content that no longer exists.
        for table in (
            "media_parts",
            "media_item_categories",
            "media_favorites",
            "media_watch_progress",
            "media_watch_history",
            "media_notifications",
            "media_notification_deliveries",
        ):
            c.execute(f"DELETE FROM {table} WHERE media_id=?", (media_id,))
        c.execute(
            "DELETE FROM media_items WHERE lower(code)=lower(?)",
            (code,),
        )
        changed = c.rowcount == 1
        con.commit()
        return changed
    except Exception:
        con.rollback()
        logger.exception("Universal media o'chirilmadi [%s]", code)
        return False
    finally:
        con.close()


def add_anime(code, title, desc, poster, genres, season, ova, voice, minstatus, by):
    con = db(); c = con.cursor()
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        code = str(code or "").strip()
        if not code:
            code = next_content_code(c)
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", code):
            return False
        c.execute(
            "SELECT 1 FROM anime WHERE lower(code)=lower(?) "
            "UNION ALL SELECT 1 FROM media_items WHERE lower(code)=lower(?) LIMIT 1",
            (code, code),
        )
        if c.fetchone():
            return False
        c.execute(
            "INSERT INTO anime(code,title,description,poster_id,genres,season,ova_info,"
            "voice,min_status,added_by,added_date) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (code, title, desc, poster, genres, season, ova, voice, minstatus, by, now),
        )
        _mirror_anime_row(c, code)
        con.commit(); return True
    except sqlite3.IntegrityError:
        return False
    finally:
        con.close()


def get_anime(code):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM anime WHERE code=?", (code,))
    r = c.fetchone(); con.close()
    return dict(r) if r else None


def get_anime_by_id(anime_id):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM anime WHERE id=?", (anime_id,))
    r = c.fetchone(); con.close()
    return dict(r) if r else None


def del_anime(code):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT id FROM media_items WHERE code=? AND media_type='anime'", (code,)
    )
    media_row = c.fetchone()
    media_id = media_row["id"] if media_row else None
    c.execute("DELETE FROM episodes WHERE anime_code=?", (code,))
    for table in (
        "favorites", "watch_progress", "watch_history",
        "anime_notifications", "notification_deliveries",
        "anime_view_dedupe",
    ):
        c.execute(f"DELETE FROM {table} WHERE anime_code=?", (code,))
    if media_id is not None:
        for table in (
            "media_parts", "media_item_categories", "media_favorites",
            "media_watch_progress", "media_watch_history",
            "media_notifications", "media_notification_deliveries",
        ):
            c.execute(f"DELETE FROM {table} WHERE media_id=?", (media_id,))
    c.execute("DELETE FROM anime WHERE code=?", (code,))
    c.execute("DELETE FROM media_items WHERE code=? AND media_type='anime'", (code,))
    n = c.rowcount; con.commit(); con.close(); return n > 0


def upd_anime(code, field, val):
    ok = {"title","description","poster_id","genres","season","ova_info","voice",
          "min_status", "age_limit", "episode_total", "trailer_id", "trailer_type"}
    if field not in ok: return False
    con = db(); c = con.cursor()
    c.execute(f"UPDATE anime SET {field}=? WHERE code=?", (val, code))
    _mirror_anime_row(c, code)
    con.commit(); con.close(); return True


def pop_anime(n=10):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT code,title,views FROM anime ORDER BY COALESCE(views,0) DESC, id DESC LIMIT ?",
        (n,),
    )
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def ranked_anime(kind="popular", page=0, per=10):
    """Legacy nomi saqlangan universal katalog reyting adapteri."""
    page = max(0, int(page))
    order = (
        "COALESCE(views,0) DESC, id DESC"
        if kind == "popular"
        else "added_date DESC, id DESC"
    )
    con = db(); c = con.cursor()
    c.execute(
        f"SELECT id,code,title,views,media_type FROM media_items "
        f"WHERE active=1 ORDER BY {order} LIMIT ? OFFSET ?",
        (per, page * per),
    )
    rows = [dict(x) for x in c.fetchall()]
    c.execute("SELECT COUNT(*) FROM media_items WHERE active=1")
    total = c.fetchone()[0]
    con.close()
    return rows, total


def new_anime(n=10):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT id,code,title FROM anime ORDER BY added_date DESC, id DESC LIMIT ?",
        (n,),
    )
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def anime_list_keyboard(rows, kind, page, total):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        suffix = ""
        if kind == "popular":
            suffix = f" · 👁 {int(row.get('views') or 0)}"
        kb.add(types.InlineKeyboardButton(
            f"{media_type_icon(row.get('media_type'))} "
            f"{(row.get('title') or row.get('code') or 'Media')[:45]}{suffix}",
            callback_data=f"ANID_{row['id']}",
        ))
    total_pages = max(1, (total + 9) // 10)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            "⬅️ Oldingi", callback_data=f"LIST_{kind.upper()}_{page - 1}",
        ))
    if page + 1 < total_pages:
        nav.append(types.InlineKeyboardButton(
            "➡️ Keyingi", callback_data=f"LIST_{kind.upper()}_{page + 1}",
        ))
    if nav:
        kb.row(*nav)
    return kb


def category_keyboard(genre, page=0):
    rows = anime_by_genre(genre, limit=10, offset=page * 10)
    total = genre_count(genre)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        kb.add(types.InlineKeyboardButton(
            f"🎬 {(row.get('title') or row.get('code') or 'Anime')[:45]}",
            callback_data=f"ANID_{row['id']}",
        ))
    total_pages = max(1, (total + 9) // 10)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            "⬅️ Oldingi", callback_data=f"CATP|{genre}|{page - 1}",
        ))
    if page + 1 < total_pages:
        nav.append(types.InlineKeyboardButton(
            "➡️ Keyingi", callback_data=f"CATP|{genre}|{page + 1}",
        ))
    if nav:
        kb.row(*nav)
    kb.add(types.InlineKeyboardButton("🔙 Kategoriyalar", callback_data="CATS"))
    return kb, total, total_pages


def get_anime_by_code_input(value):
    value = str(value or "").strip()
    if not value:
        return None
    anime = get_anime(value)
    if anime:
        return anime
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM anime WHERE lower(code)=lower(?)", (value,))
    row = c.fetchone(); con.close()
    return dict(row) if row else None


def normalize_search_text(value):
    """Qidiruvni Unicode, bo'sh joy va apostrof bo'yicha bir xil qiladi."""
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.replace("’", "'").replace("ʻ", "'").replace("ʼ", "'")
    value = value.replace("`", "'").replace("′", "'")
    return " ".join(value.casefold().split())


def format_age_category(value):
    """Anime sahifasida yosh toifasini yagona ko'rinishda chiqaradi."""
    value = str(value or "").strip()
    if value.casefold() in {"", "-", "—", "belgilanmagan", "noma'lum", "unknown"}:
        return "Belgilanmagan"
    return value


def search_anime(q, limit=15):
    needle = normalize_search_text(q)
    if not needle:
        return []
    con = db(); c = con.cursor()
    c.execute("SELECT id,code,title FROM anime ORDER BY added_date DESC, id DESC")
    rows = [dict(x) for x in c.fetchall()]
    con.close()
    exact_code = []
    exact_title = []
    partial = []
    for row in rows:
        code = normalize_search_text(row.get("code"))
        title = normalize_search_text(row.get("title"))
        if code == needle:
            exact_code.append(row)
        elif title == needle:
            exact_title.append(row)
        elif needle in code or needle in title:
            partial.append(row)
    return (exact_code + exact_title + partial)[:limit]


def anime_by_genre(genre, limit=None, offset=0):
    con = db(); c = con.cursor()
    sql = (
        "SELECT id,code,title,media_type FROM media_items "
        "WHERE active=1 AND genres LIKE ? "
        "ORDER BY added_date DESC, id DESC"
    )
    params = [f"%{genre}%"]
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
    c.execute(sql, params)
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def genre_count(genre):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT COUNT(*) FROM media_items WHERE active=1 AND genres LIKE ?",
        (f"%{genre}%",),
    )
    count = c.fetchone()[0]
    con.close()
    return count


def inc_views(code, uid=None):
    """Bir foydalanuvchining bir kundagi qayta ochishlarini takror sanamaydi."""
    con = db(); c = con.cursor()
    if uid is None:
        c.execute("UPDATE anime SET views=COALESCE(views,0)+1 WHERE code=?", (code,))
        changed = c.rowcount == 1
    else:
        today = local_today().strftime("%Y-%m-%d")
        now = local_now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute(
            "INSERT OR IGNORE INTO anime_view_dedupe(user_id,anime_code,viewed_date,viewed_at)"
            " VALUES(?,?,?,?)",
            (uid, code, today, now),
        )
        changed = c.rowcount == 1
        if changed:
            c.execute("UPDATE anime SET views=COALESCE(views,0)+1 WHERE code=?", (code,))
    con.commit(); con.close()
    return changed


def is_favorite(uid, code):
    media = get_media_item(code)
    if media:
        return is_media_favorite(uid, media["id"])
    con = db(); c = con.cursor()
    c.execute("SELECT 1 FROM favorites WHERE user_id=? AND anime_code=?", (uid, code))
    result = c.fetchone() is not None
    con.close()
    return result


def toggle_favorite(uid, code):
    media = get_media_item(code)
    if media:
        enabled = toggle_media_favorite(uid, media["id"])
        # Keep the legacy table in sync for old exports and callbacks.
        con = db(); c = con.cursor()
        if enabled:
            c.execute(
                "INSERT OR IGNORE INTO favorites(user_id,anime_code,added_at) VALUES(?,?,?)",
                (uid, code, local_now().strftime("%Y-%m-%d %H:%M:%S")),
            )
        else:
            c.execute("DELETE FROM favorites WHERE user_id=? AND anime_code=?", (uid, code))
        con.commit(); con.close()
        return enabled
    con = db(); c = con.cursor()
    c.execute("SELECT 1 FROM favorites WHERE user_id=? AND anime_code=?", (uid, code))
    if c.fetchone():
        c.execute("DELETE FROM favorites WHERE user_id=? AND anime_code=?", (uid, code))
        enabled = False
    else:
        c.execute(
            "INSERT OR IGNORE INTO favorites(user_id,anime_code,added_at) VALUES(?,?,?)",
                (uid, code, local_now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        enabled = True
    con.commit(); con.close()
    return enabled


def anime_notifications_enabled(uid, code):
    media = get_media_item(code)
    if media:
        return media_notifications_enabled(uid, media["id"])
    con = db(); c = con.cursor()
    c.execute(
        "SELECT enabled FROM anime_notifications WHERE user_id=? AND anime_code=?",
        (uid, code),
    )
    row = c.fetchone()
    if row is not None:
        result = bool(row["enabled"])
    else:
        result = False
    con.close()
    return result


def toggle_anime_notification(uid, code):
    media = get_media_item(code)
    if media:
        enabled = toggle_media_notification(uid, media["id"])
        con = db(); c = con.cursor()
        c.execute(
            "INSERT INTO anime_notifications(user_id,anime_code,enabled,added_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id,anime_code) DO UPDATE SET enabled=excluded.enabled",
            (uid, code, int(enabled), local_now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit(); con.close()
        return enabled
    con = db(); c = con.cursor()
    c.execute(
        "SELECT enabled FROM anime_notifications WHERE user_id=? AND anime_code=?",
        (uid, code),
    )
    row = c.fetchone()
    enabled = not bool(row["enabled"]) if row else True
    c.execute(
        "INSERT INTO anime_notifications(user_id,anime_code,enabled,added_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,anime_code) DO UPDATE SET enabled=excluded.enabled",
        (uid, code, int(enabled), local_now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    con.commit(); con.close()
    return enabled


def set_global_notifications(uid, enabled):
    con = db(); c = con.cursor()
    c.execute(
        "UPDATE users SET notifications_enabled=? WHERE user_id=?",
        (int(bool(enabled)), uid),
    )
    con.commit(); con.close()
    return bool(enabled)


def list_favorites(uid):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT m.code,m.title,m.poster_id,m.media_type,f.added_at "
        "FROM media_favorites f JOIN media_items m ON m.id=f.media_id "
        "WHERE f.user_id=? AND m.active=1 ORDER BY f.added_at DESC",
        (uid,),
    )
    rows = [dict(x) for x in c.fetchall()]
    con.close()
    return rows


def record_watch(uid, code, ep_num, ep_type="season"):
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    media = get_media_item(code)
    if media:
        record_media_watch(
            uid, media["id"], ep_num,
            "ova" if ep_type == "ova" else ("episode" if ep_type == "season" else ep_type),
            1,
        )
    con = db(); c = con.cursor()
    c.execute(
        "INSERT INTO watch_progress(user_id,anime_code,ep_type,ep_num,watched_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(user_id,anime_code,ep_type) DO UPDATE SET ep_num=excluded.ep_num,watched_at=excluded.watched_at",
        (uid, code, ep_type, int(ep_num), now),
    )
    c.execute(
        "INSERT INTO watch_history(user_id,anime_code,ep_type,ep_num,watched_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(user_id,anime_code,ep_type,ep_num) DO UPDATE SET watched_at=excluded.watched_at",
        (uid, code, ep_type, int(ep_num), now),
    )
    con.commit(); con.close()
    return True


def get_watch_progress(uid, limit=10):
    rows = []
    for row in get_media_watch_progress(uid, limit):
        row["anime_code"] = row.get("code")
        row["ep_type"] = "ova" if row.get("part_type") == "ova" else row.get("part_type", "part")
        row["ep_num"] = row.get("part_number")
        rows.append(row)
    return rows


def get_watch_history(uid, limit=20):
    rows = []
    for row in get_media_watch_history(uid, limit):
        row["anime_code"] = row.get("code")
        row["ep_type"] = "ova" if row.get("part_type") == "ova" else row.get("part_type", "part")
        row["ep_num"] = row.get("part_number")
        rows.append(row)
    return rows


def log_admin_action(admin_id, action, anime_code=None, ep_type=None, ep_num=None):
    try:
        con = db(); c = con.cursor()
        c.execute(
            "INSERT INTO admin_actions(admin_id,action,anime_code,ep_type,ep_num,created_at) "
            "VALUES(?,?,?,?,?,?)",
            (
                admin_id, action, anime_code, ep_type, ep_num,
                local_now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        con.commit(); con.close()
    except Exception:
        logger.exception("Admin harakatini yozib bo'lmadi")


def get_admin_actions(limit=30):
    con = db(); c = con.cursor()
    c.execute(
        """
        SELECT aa.*, u.full_name, u.username
          FROM admin_actions aa
          LEFT JOIN users u ON u.user_id=aa.admin_id
         ORDER BY aa.id DESC LIMIT ?
        """,
        (int(limit),),
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def random_anime():
    """Legacy nomli universal random-content adapter."""
    con = db(); c = con.cursor()
    c.execute(
        "SELECT id,code,title,media_type FROM media_items "
        "WHERE active=1 ORDER BY RANDOM() LIMIT 1"
    )
    row = c.fetchone(); con.close()
    return dict(row) if row else None


def _notification_candidates(code):
    con = db(); c = con.cursor()
    c.execute(
        """
        SELECT DISTINCT u.user_id
          FROM users u
          LEFT JOIN favorites f
            ON f.user_id=u.user_id AND f.anime_code=?
          LEFT JOIN anime_notifications n
            ON n.user_id=u.user_id AND n.anime_code=?
         WHERE u.blocked=0
           AND COALESCE(u.notifications_enabled,1)=1
           AND (f.user_id IS NOT NULL OR n.enabled=1)
        """,
        (code, code),
    )
    ids = [row["user_id"] for row in c.fetchall()]
    con.close()
    return ids


def notify_new_episode(code, ep_num, ep_type="season", season_number=1, part_type=None):
    """Universal media bo'limi uchun dublikatlarsiz bildirishnoma yuboradi."""
    media = get_media_item(code)
    if not media:
        return
    con = db()
    c = con.cursor()
    c.execute(
        """
        SELECT DISTINCT u.user_id
          FROM users u
          LEFT JOIN media_favorites f
            ON f.user_id=u.user_id AND f.media_id=?
          LEFT JOIN media_notifications n
            ON n.user_id=u.user_id AND n.media_id=? AND n.enabled=1
          LEFT JOIN favorites lf
            ON lf.user_id=u.user_id AND lf.anime_code=?
          LEFT JOIN anime_notifications ln
            ON ln.user_id=u.user_id AND ln.anime_code=? AND ln.enabled=1
         WHERE u.blocked=0
           AND COALESCE(u.notifications_enabled,1)=1
           AND (f.user_id IS NOT NULL OR n.user_id IS NOT NULL
                OR lf.user_id IS NOT NULL OR ln.user_id IS NOT NULL)
        """,
        (media["id"], media["id"], code, code),
    )
    recipients = [row["user_id"] for row in c.fetchall()]
    con.close()
    if not recipients:
        return
    season = season_number or media.get("season") or "1"
    part_type = part_type or ("ova" if ep_type == "ova" else "episode")
    ep_label = (
        f"{season}-fasl • {ep_num}-bo'lim"
        if ep_type == "season" else
        f"{media_part_label(part_type)} • {ep_num}-bo'lim"
    )
    text = (
        "🔔 *Yangi media bo'limi*\n\n"
        f"{media_type_icon(media.get('media_type'))} *{media.get('title') or code}*\n"
        f"📺 {ep_label}\n\n"
        "Yangi bo'lim tomosha qilishga tayyor."
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "▶️ Tomosha qilish",
        callback_data=(
            f"MED_WATCH|{media['id']}|{part_type}|{int(season_number or 1)}|{int(ep_num)}"
            if media else f"WATCH_{code}|{ep_type}|{int(ep_num)}"
        ),
    ))
    for index, uid in enumerate(recipients, 1):
        con = db(); c = con.cursor()
        c.execute(
            "INSERT OR IGNORE INTO media_notification_deliveries"
            "(user_id,media_id,part_type,season_number,part_number,sent_at) "
            "VALUES(?,?,?,?,?,?)",
            (uid, media["id"], part_type, int(season_number or 1), int(ep_num),
             local_now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        should_send = c.rowcount == 1
        c.execute(
            "INSERT OR IGNORE INTO notification_deliveries"
            "(user_id,anime_code,ep_type,ep_num,sent_at) VALUES(?,?,?,?,?)",
            (uid, code, ep_type, int(ep_num), local_now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        con.commit(); con.close()
        if not should_send:
            continue
        try:
            bot.send_message(uid, text, reply_markup=kb)
        except Exception as exc:
            logger.warning("Bildirishnoma yuborilmadi [%s]: %s", uid, exc)
            if any(word in str(exc).lower() for word in ("blocked", "deactivated", "chat not found")):
                con = db(); c = con.cursor()
                c.execute("UPDATE users SET blocked=1 WHERE user_id=?", (uid,))
                con.commit(); con.close()
        if index % 20 == 0:
            time.sleep(1)


# ============================================================
#  EPISODE HELPERS
# ============================================================

def add_ep(code, num, etype, fid, ftype):
    con = db(); c = con.cursor()
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute(
            "INSERT INTO episodes(anime_code,ep_num,ep_type,file_id,file_type,added_date)"
            " VALUES(?,?,?,?,?,?)",
            (code, num, etype, fid, ftype, now),
        )
        c.execute(
            "INSERT OR IGNORE INTO media_parts"
            "(media_id,part_type,season_number,part_number,file_id,file_type,added_date,active)"
            " SELECT id,?,?,?,?,?,?,1 FROM media_items WHERE code=? AND media_type='anime'",
            (
                "ova" if etype == "ova" else "episode", 1, num,
                fid, ftype, now, code,
            ),
        )
        con.commit(); return True
    except sqlite3.IntegrityError:
        con.rollback()
        logger.warning("Takroriy qism qo'shish rad etildi: %s/%s/%s", code, etype, num)
        return False
    except Exception as e:
        con.rollback()
        logger.error(f"ep qo'shish: {e}")
        return False
    finally:
        con.close()


def get_eps(code, etype="season", page=0, per=10):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT * FROM episodes WHERE anime_code=? AND ep_type=? ORDER BY ep_num ASC LIMIT ? OFFSET ?",
        (code, etype, per, page * per),
    )
    r = [dict(x) for x in c.fetchall()]; con.close(); return r


def ep_count(code, etype="season"):
    con = db(); c = con.cursor()
    c.execute("SELECT COUNT(*) FROM episodes WHERE anime_code=? AND ep_type=?", (code, etype))
    n = c.fetchone()[0]; con.close(); return n


def next_ep_num(code, etype="season"):
    con = db(); c = con.cursor()
    c.execute("SELECT MAX(ep_num) FROM episodes WHERE anime_code=? AND ep_type=?", (code, etype))
    mx = c.fetchone()[0]; con.close()
    return (mx or 0) + 1


def get_ep(code, num, etype="season"):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM episodes WHERE anime_code=? AND ep_num=? AND ep_type=?", (code, num, etype))
    r = c.fetchone(); con.close()
    return dict(r) if r else None


def del_ep(code, num, etype="season"):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM episodes WHERE anime_code=? AND ep_num=? AND ep_type=?", (code, num, etype))
    c.execute(
        "UPDATE media_parts SET active=0 WHERE media_id=("
        "SELECT id FROM media_items WHERE code=? AND media_type='anime') "
        "AND part_type=? AND part_number=?",
        (code, "ova" if etype == "ova" else "episode", num),
    )
    deleted = c.rowcount
    for table in ("watch_progress", "watch_history", "notification_deliveries"):
        c.execute(
            f"DELETE FROM {table} WHERE anime_code=? AND ep_num=? AND ep_type=?",
            (code, num, etype),
        )
    con.commit(); con.close(); return deleted > 0


# ============================================================
#  SPAM
# ============================================================
SPAM_LIM = 5
SPAM_WIN = 10

def check_spam(uid):
    con = db(); c = con.cursor(); now = time.time()
    c.execute("SELECT last_time,cnt FROM spam_log WHERE user_id=?", (uid,))
    row = c.fetchone()
    if row:
        if now - row["last_time"] < SPAM_WIN:
            if row["cnt"] >= SPAM_LIM:
                con.close(); return False
            c.execute("UPDATE spam_log SET cnt=cnt+1 WHERE user_id=?", (uid,))
        else:
            c.execute("UPDATE spam_log SET last_time=?,cnt=1 WHERE user_id=?", (now, uid))
    else:
        c.execute("INSERT INTO spam_log(user_id,last_time,cnt) VALUES(?,?,1)", (uid, now))
    con.commit(); con.close(); return True


# ============================================================
#  CONSTANTS
# ============================================================
ST_EMOJI = {"user": "👤", "vip": "⭐", "premium": "💎", "admin": "🔧", "owner": "👑"}
ST_NAME  = {"user": "Oddiy", "vip": "VIP", "premium": "Premium", "admin": "Admin", "owner": "Owner"}
ST_ORDER = ["user", "vip", "premium", "admin", "owner"]

GENRES = [
    ("Action","Jangari"),("Adventure","Sarguzasht"),("Comedy","Komediya"),
    ("Drama","Drama"),("Romance","Romantika"),("Fantasy","Fantastika"),
    ("Sci-Fi","Ilmiy fantastika"),("Isekai","Boshqa dunyoga tushib qolish"),
    ("Slice of Life","Kundalik hayot"),("Mystery","Sirli"),
    ("Psychological","Psixologik"),("Horror","Qo'rqinchli"),
    ("Supernatural","G'ayritabiiy"),("Sports","Sport"),
    ("School","Maktab"),("Historical","Tarixiy"),
    ("Mecha","Robotlar"),("Music","Musiqa"),
    ("Magic","Sehr"),("Military","Harbiy"),
    ("Thriller","Triller"),("Detective","Detektiv"),
    ("Survival","Tirik qolish"),("Harem","Harem"),
    ("Reverse Harem","Teskari Harem"),("Ecchi","Yengil kattalar"),
]


def can_access(user_st, min_st):
    try:
        return ST_ORDER.index(user_st) >= ST_ORDER.index(min_st)
    except ValueError:
        return False


# ============================================================
#  STATES
# ============================================================
STATES: dict = {}
MEDIA_GROUPS: dict = {}
MG_LOCK = threading.Lock()


def sset(uid, state, data=None):
    STATES[uid] = {"state": state, "data": data or {}}


def sget(uid):
    return STATES.get(uid, {})


def sclear(uid):
    STATES.pop(uid, None)


def supd(uid, key, val):
    if uid not in STATES:
        STATES[uid] = {"state": "", "data": {}}
    STATES[uid]["data"][key] = val


# ============================================================
#  MEDIA GROUP
# ============================================================

def _process_media_group(mgid):
    with MG_LOCK:
        mg = MEDIA_GROUPS.pop(mgid, None)
    if not mg:
        return
    uid      = mg["uid"]
    chat_id  = mg["chat_id"]
    d        = mg["data"]
    files    = mg["files"]
    code     = d["anime_code"]
    et       = d["ep_type"]
    tname    = "OVA" if et == "ova" else "Asosiy"

    ok_count = 0
    start_ep = next_ep_num(code, et)
    for fid, ftype in files:
        nn = next_ep_num(code, et)
        if add_ep(code, nn, et, fid, ftype):
            ok_count += 1
            log_admin_action(uid, "episode_added", code, et, nn)
            threading.Thread(
                target=notify_new_episode,
                args=(code, nn, et),
                daemon=True,
            ).start()

    total_now = ep_count(code, et)
    end_ep = start_ep + ok_count - 1

    # Avtopost taklifi
    if _can_use_autopost(uid) and get_autopost_channels(only_active=True):
        sset(uid, "ap_ep_wait", {
            "anime_code": code,
            "anime_title": d["anime_title"],
            "ep_num": end_ep,
            "ep_type": et,
        })
        active_chs = get_autopost_channels(only_active=True)
        safe(bot.send_message, chat_id,
            f"✅ *{ok_count} ta qism qo'shildi!*\n\n"
            f"🎬 Anime: *{d['anime_title']}*\n"
            f"📹 Tur: *{tname}*\n"
            f"🔢 Qo'shildi: *{start_ep} — {end_ep}*\n"
            f"📊 Jami bazada: *{total_now}* ta qism\n\n"
            f"📡 *Kanalga e'lon joylaysizmi?*",
            reply_markup=_autopost_offer_kb(len(active_chs)))
    else:
        sset(uid, "ep_file", d)
        safe(bot.send_message, chat_id,
            f"✅ *{ok_count} ta qism qo'shildi!*\n\n"
            f"🎬 Anime: *{d['anime_title']}*\n"
            f"📹 Tur: *{tname}*\n"
            f"🔢 Qo'shildi: *{start_ep} — {end_ep}*\n"
            f"📊 Jami bazada: *{total_now}* ta qism\n\n"
            f"⬆️ Yana fayl yuboring — davom ettiradi.\n"
            f"Tugatish uchun '🔙 Orqaga' ni bosing.")


# ============================================================
#  AVTOPOST TUGMALAR HELPERS
# ============================================================

def _autopost_offer_kb(active_ch_count):
    """Avtopost taklifi tugmalari."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    if active_ch_count > 1:
        kb.add(
            types.InlineKeyboardButton("👀 Preview", callback_data="AP_PREVIEW"),
            types.InlineKeyboardButton("✏️ Postni tahrirlash", callback_data="AP_EDIT"),
            types.InlineKeyboardButton("📡 Barcha faol kanallarga", callback_data="AP_ALL"),
            types.InlineKeyboardButton("📡 Kanalni tanlash", callback_data="AP_SELECT"),
            types.InlineKeyboardButton("❌ Bekor qilish", callback_data="AP_CANCEL"),
        )
    else:
        kb.add(
            types.InlineKeyboardButton("👀 Preview", callback_data="AP_PREVIEW"),
            types.InlineKeyboardButton("✏️ Postni tahrirlash", callback_data="AP_EDIT"),
            types.InlineKeyboardButton("📡 Joylash", callback_data="AP_ALL"),
            types.InlineKeyboardButton("❌ Bekor qilish", callback_data="AP_CANCEL"),
        )
    return kb


def _autopost_channel_select_kb(channels):
    """Kanal tanlash tugmalari."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        kb.add(types.InlineKeyboardButton(
            f"📡 {ch['channel_name']}", callback_data=f"APC_{ch['channel_id']}"
        ))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="AP_CANCEL"))
    return kb


def _restore_episode_add_state(uid, draft):
    """Avtopost taklifi yakunlangach ham keyingi video uchun oqimni saqlaydi."""
    media_code = draft.get("media_code") or draft.get("anime_code")
    media = get_media_item(media_code) if media_code else None
    if media and media.get("media_type") != "anime":
        season_number = draft.get("season_number") or 1
        part_type = draft.get("ep_type") or "part"
        media = get_media_item(media_code) or {}
        next_number = next_media_part_number(
            media["id"],
            part_type,
            season_number,
        )
        sset(uid, "media_part_file_wait", {
            "media_id": media["id"],
            "media_code": media_code,
            "part_type": part_type,
            "season_number": season_number,
            "part_number": next_number,
        })
        return True
    if not draft or not draft.get("anime_code") or not draft.get("ep_type"):
        sclear(uid)
        return False
    sset(uid, "ep_file", {
        "anime_code": draft["anime_code"],
        "anime_title": draft.get("anime_title") or draft["anime_code"],
        "ep_type": draft["ep_type"],
    })
    return True


def _finish_autopost_action(uid, draft):
    """Avtopostdan keyin qism qo'shish rejimini saqlab qoladi."""
    if draft and draft.get("post_type") == "new_episode":
        _restore_episode_add_state(uid, draft)
    else:
        sclear(uid)


# ============================================================
#  KEYBOARDS
# ============================================================

def main_kb(uid):
    st = get_status(uid)
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("🔍 Qidirish", "📚 Kategoriyalar")
    kb.add("🔥 Trendda", "🆕 Yangi qo'shilganlar")
    kb.add("🎲 Tasodifiy tanlov", "👤 Profilim")
    kb.add("🎁 Kunlik bonus", "ℹ️ Yordam")
    kb.add("👥 Referal")
    if st in ("vip", "premium", "admin", "owner"):
        kb.add(types.KeyboardButton("💎 Premium"))
    if st in ("admin", "owner"):
        kb.add(types.KeyboardButton("⚙️ Admin panel"))
    return kb


def admin_kb(uid=None):
    """
    Admin paneli klaviaturasi — yagona universal kontent boshqaruv tizimi.
    uid berilsa — faqat ruxsat berilgan tugmalar ko'rsatiladi.
    uid=None yoki owner — barcha tugmalar ko'rsatiladi.
    """
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if uid is None or uid == OWNER_ID:
        kb.add("➕ Kontent qo'shish", "🎬 Qismlar boshqaruvi")
        kb.add("✏️ Tahrirlash", "🗑️ O'chirish")
        kb.add("📚 Kutubxona", "⚙️ Sozlamalar")
        kb.add("📊 Statistika", "📢 Broadcast")
        kb.add("✍️ Qo'lda post", "📋 Qo'lda postlar")
        kb.add("👥 Foydalanuvchilar", "📜 Admin harakatlari")
        kb.add("📡 Avtoposting", "🔙 Orqaga")
        return kb
    # Ruxsatli tugmalar
    row1 = []
    if admin_media_perm(uid, "add"): row1.append("➕ Kontent qo'shish")
    if admin_media_perm(uid, "parts"): row1.append("🎬 Qismlar boshqaruvi")
    if row1: kb.add(*row1)
    if admin_media_perm(uid, "add"):
        kb.add("📚 Kutubxona", "⚙️ Sozlamalar")
    row2 = []
    if admin_media_perm(uid, "edit"): row2.append("✏️ Tahrirlash")
    if admin_media_perm(uid, "delete"): row2.append("🗑️ O'chirish")
    if row2: kb.add(*row2)
    row3 = []
    if admin_has_perm(uid, "stats"):     row3.append("📊 Statistika")
    if admin_has_perm(uid, "broadcast"): row3.append("📢 Broadcast")
    if row3: kb.add(*row3)
    if admin_has_perm(uid, "autopost"):
        kb.add("📡 Avtoposting")
    if admin_has_perm(uid, "user_manage"):
        kb.add("👥 Foydalanuvchilar")
    row_mp = []
    if admin_has_perm(uid, "manual_post"):
        row_mp.append("✍️ Qo'lda post")
    if admin_has_perm(uid, "manual_post_history"):
        row_mp.append("📋 Qo'lda postlar")
    if row_mp:
        kb.add(*row_mp)
    kb.add("⚙️ Sozlamalar", "🔙 Orqaga")
    return kb


def sub_kb():
    chs = get_channels(only_active=True)
    kb = types.InlineKeyboardMarkup()
    for ch in chs:
        icon = PLATFORM_ICONS.get(ch.get('platform', 'telegram'), '📢')
        kb.add(types.InlineKeyboardButton(f"{icon} {ch['channel_name']}", url=ch["channel_url"]))
    kb.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return kb


def ep_list_kb(code, etype, page, total_pages, has_other):
    kb = types.InlineKeyboardMarkup(row_width=5)
    episodes = get_eps(code, etype, page)
    btns = [
        types.InlineKeyboardButton(str(e["ep_num"]),
            callback_data=f"SEP|{code}|{e['ep_num']}|{etype}|{page}")
        for e in episodes
    ]
    if btns: kb.add(*btns)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton("⬅️ Oldingi", callback_data=f"EPG|{code}|{etype}|{page-1}"))
    if page < total_pages - 1:
        nav.append(types.InlineKeyboardButton("➡️ Keyingi", callback_data=f"EPG|{code}|{etype}|{page+1}"))
    if nav: kb.add(*nav)
    if has_other:
        ot = "ova" if etype == "season" else "season"
        ol = "🎞️ OVA qismlari" if ot == "ova" else "📺 Asosiy qismlar"
        kb.add(types.InlineKeyboardButton(ol, callback_data=f"EPG|{code}|{ot}|0"))
    kb.add(types.InlineKeyboardButton("🔙 Anime ma'lumoti", callback_data=f"ABCK_{code}"))
    return kb


def _profile_kb(uid):
    enabled = bool((get_user(uid) or {}).get("notifications_enabled", 1))
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("❤️ Sevimlilarim", callback_data="PROFILE_FAV"),
        types.InlineKeyboardButton("🕒 Davom ettirish", callback_data="PROFILE_CONT"),
    )
    kb.add(
        types.InlineKeyboardButton("🕓 Ko'rish tarixi", callback_data="PROFILE_HISTORY"),
        types.InlineKeyboardButton("🔔 Bildirishnomalar", callback_data="PROFILE_NOTIF"),
    )
    kb.add(types.InlineKeyboardButton(
        "🔕 Barcha bildirishnomalarni o'chirish" if enabled
        else "🔔 Barcha bildirishnomalarni yoqish",
        callback_data="PROFILE_NOTIF_OFF" if enabled else "PROFILE_NOTIF_ON",
    ))
    kb.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="GO_HOME"))
    return kb


# ============================================================
#  SEND HELPERS
# ============================================================

def safe(fn, *a, **kw):
    try: return fn(*a, **kw)
    except Exception as e: logger.error(f"safe send: {e}")


def safe_edit(chat_id, mid, text, **kw):
    try:
        bot.edit_message_text(text, chat_id, mid, **kw)
    except Exception:
        safe(bot.send_message, chat_id, text, **kw)


def ep_caption(anime, ep_num, etype):
    sezon = f"Season {anime['season']}" if etype == "season" else f"OVA {ep_num}"
    return (
        f"⛩️ *Anime:* {anime['title'] or ''}\n\n"
        f"🎞️ *Qism:* {ep_num}-qism\n\n"
        f"🎭 *Janrlari:* {anime['genres'] or '—'}\n\n"
        f"📽️ *Sezon:* {sezon}\n\n"
        f"🎙️ *Ovoz:* {anime['voice'] or '—'}\n\n"
        f"📡 *Kanal:* {get_main_channel_tag()}"
    )


def _send_episode_file(chat_id, anime, ep, ep_num, etype, page=0):
    """Bitta qismni foydalanuvchiga xavfsiz yuboradi."""
    cap = ep_caption(anime, ep_num, etype)
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton(
        "📋 Qismlar ro'yxati",
        callback_data=f"EPG|{anime['code']}|{etype}|{page}",
    ))
    try:
        if ep["file_type"] == "video":
            return bot.send_video(chat_id, ep["file_id"], caption=cap, reply_markup=kb)
        if ep["file_type"] == "animation":
            return bot.send_animation(chat_id, ep["file_id"], caption=cap, reply_markup=kb)
        return bot.send_document(chat_id, ep["file_id"], caption=cap, reply_markup=kb)
    except Exception as exc:
        logger.exception("Qism yuborilmadi [%s/%s/%s]", anime.get("code"), etype, ep_num)
        safe(bot.send_message, chat_id, "❌ Qismni yuborishda xato yuz berdi.")
        return None


def _legacy_show_anime(chat_id, uid, code, edit_mid=None):
    a = get_anime_by_code_input(code)
    if not a:
        safe(bot.send_message, chat_id, "❌ Bu ma'lumot endi mavjud emas.")
        return
    code = a["code"]
    st = get_status(uid)
    ms = a.get("min_status", "user")
    if not can_access(st, ms):
        if ms == "premium":
            safe(bot.send_message, chat_id,
                "💎 *Bu anime faqat PREMIUM foydalanuvchilar uchun!*\n\n"
                "Premium foydalanuvchilar:\n"
                "• Majburiy obunasiz foydalanishi mumkin\n"
                "• VIP va Premium animelarning barchasini tomosha qilishi mumkin\n\n"
                "Premium olish uchun admin bilan bog'laning:\n👉 @nowloss")
        else:
            safe(bot.send_message, chat_id,
                "⭐ *Bu anime faqat VIP foydalanuvchilar uchun!*\n\n"
                "VIP foydalanuvchilarga maxsus eksklyuziv animelar taqdim etiladi.\n\n"
                "VIP olish uchun admin bilan bog'laning:\n👉 @nowloss\n\n"
                "💡 Yoki 50 tanga to'plang — avtomatik VIP beriladi!")
        return

    sc = ep_count(code, "season")
    oc = ep_count(code, "ova")
    counted = inc_views(code, uid)
    views = int(a.get("views") or 0) + (1 if counted else 0)

    text = (
        f"🎬 *{a['title'] or ''}*\n\n"
        f"📝 *Tavsif:*\n{a['description'] or '—'}\n\n"
        f"🎭 *Janrlari:* {a['genres'] or '—'}\n"
        f"📺 *Fasl:* {a['season'] or '1'}\n"
        f"🎙️ *Ovoz:* {a['voice'] or '—'}\n"
        f"🔞 *Yosh toifasi:* {format_age_category(a.get('age_limit'))}\n"
        f"📊 *Qismlar:* {sc} ta asosiy"
        + (f", {oc} ta OVA\n" if oc else "\n")
        + f"👁 *Ko'rishlar:* {views}\n"
    )
    if a.get("ova_info"):
        text += f"🎞️ *OVA:* {a['ova_info']}\n"

    kb = types.InlineKeyboardMarkup(row_width=2)
    if sc: kb.add(types.InlineKeyboardButton(f"📺 Qismlar ({sc})", callback_data=f"EPG|{code}|season|0"))
    if oc: kb.add(types.InlineKeyboardButton(f"🎞️ OVA ({oc})", callback_data=f"EPG|{code}|ova|0"))
    if not sc and not oc:
        text += "\n⚠️ Hozircha qism yo'q."
    favorite_label = "💔 Sevimlilardan olib tashlash" if is_favorite(uid, code) else "❤️ Sevimliga qo'shish"
    notification_label = (
        "🔕 Bildirishnomani o'chirish"
        if anime_notifications_enabled(uid, code)
        else "🔔 Bildirishnomani yoqish"
    )
    kb.add(
        types.InlineKeyboardButton(favorite_label, callback_data=f"FAV_{code}"),
        types.InlineKeyboardButton(notification_label, callback_data=f"ANOTIF_{code}"),
    )
    username = (BOT_USERNAME or os.environ.get("BOT_USERNAME", "anibestuzbbot")).lstrip("@")
    kb.add(types.InlineKeyboardButton(
        "📤 Ulashish",
        url=f"https://t.me/{username}?start={code}",
    ))
    kb.add(types.InlineKeyboardButton("🎲 Boshqa anime", callback_data="RANDOM_ANIME"))
    kb.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="GO_HOME"))

    if a.get("poster_id"):
        safe(bot.send_photo, chat_id, a["poster_id"], caption=text, reply_markup=kb)
    elif edit_mid:
        try: bot.edit_message_text(text, chat_id, edit_mid, reply_markup=kb)
        except Exception: safe(bot.send_message, chat_id, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


def show_eps(chat_id, uid, code, etype, page, edit_mid=None):
    a = get_anime_by_code_input(code)
    if not a:
        media = get_media_item(code)
        if media:
            media_part_type = "ova" if etype == "ova" else "episode"
            parts = get_media_parts(media["id"], media_part_type)
            if parts:
                _show_media_parts(
                    chat_id, uid, media["id"], media_part_type, page,
                    edit_mid=edit_mid,
                )
        return
    PER = 10
    cnt = ep_count(code, etype)
    if cnt == 0:
        tname = "OVA" if etype == "ova" else "Asosiy"
        safe(bot.send_message, chat_id, f"❌ {tname} qism yo'q.")
        return
    total_pages = (cnt + PER - 1) // PER
    page = max(0, min(page, total_pages - 1))
    other_type = "ova" if etype == "season" else "season"
    has_other = ep_count(code, other_type) > 0
    tname = "🎞️ OVA qismlari" if etype == "ova" else "📺 Asosiy qismlar"
    text = f"🎬 *{a['title']}*\n{tname}\n\nQismni tanlang:\n📄 Sahifa: {page+1}/{total_pages}"
    kb = ep_list_kb(code, etype, page, total_pages, has_other)
    if edit_mid:
        try: bot.edit_message_text(text, chat_id, edit_mid, reply_markup=kb)
        except Exception: safe(bot.send_message, chat_id, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


# ============================================================
#  BACKUP HELPERS
# ============================================================

def create_backup():
    try:
        con = db(); c = con.cursor()

        c.execute("SELECT user_id,username,full_name,status,vip_expires,premium_expires,"
                  "coins,ref_code,referred_by,last_bonus,join_date,last_active,blocked,"
                  "notifications_enabled FROM users")
        users = [dict(r) for r in c.fetchall()]

        c.execute("SELECT user_id,added_by,added_date FROM admins")
        admins = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM admin_permissions")
        admin_perms = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM anime")
        animes = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM episodes")
        episodes = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM channels")
        channels = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM autopost_channels")
        autopost_chs = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM autopost_settings")
        autopost_settings = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM spam_log")
        spam_log = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM autopost_history")
        autopost_history = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM manual_posts")
        manual_posts = [dict(r) for r in c.fetchall()]

        c.execute("SELECT * FROM manual_post_deliveries")
        manual_post_deliveries = [dict(r) for r in c.fetchall()]
        c.execute("SELECT * FROM media_categories")
        media_categories = [dict(r) for r in c.fetchall()]
        c.execute("SELECT * FROM media_items")
        media_items = [dict(r) for r in c.fetchall()]
        extra_tables = {}
        for table in (
            "favorites", "watch_progress", "watch_history",
            "anime_notifications", "notification_deliveries",
            "anime_view_dedupe", "admin_actions",
            "media_parts", "media_item_categories", "media_favorites",
            "media_watch_progress", "media_watch_history",
            "media_notifications", "media_notification_deliveries",
        ):
            c.execute(f"SELECT * FROM {table}")
            extra_tables[table] = [dict(r) for r in c.fetchall()]

        con.close()

        backup_data = {
            "backup_version": "2.0",
            "created_at": local_now().strftime("%Y-%m-%d %H:%M:%S"),
            "bot": "ANIBEST",
            "stats": {
                "users": len(users),
                "admins": len(admins),
                "animes": len(animes),
                "episodes": len(episodes),
                "channels": len(channels),
                "autopost_channels": len(autopost_chs),
                "spam_log": len(spam_log),
                "media_items": len(media_items),
                "media_parts": len(extra_tables.get("media_parts", [])),
            },
            "data": {
                "users": users,
                "admins": admins,
                "admin_permissions": admin_perms,
                "animes": animes,
                "episodes": episodes,
                "channels": channels,
                "autopost_channels": autopost_chs,
                "autopost_settings": autopost_settings,
                "autopost_history": autopost_history,
                "manual_posts": manual_posts,
                "manual_post_deliveries": manual_post_deliveries,
                "media_categories": media_categories,
                "media_items": media_items,
                "spam_log": spam_log,
                **extra_tables,
            }
        }

        fname = local_now().strftime("anibest_backup_%Y-%m-%d_%H-%M.json")
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)

        fsize = os.path.getsize(fname)
        fsize_kb = round(fsize / 1024, 1)

        LAST_BACKUP_INFO.update({
            "date": backup_data["created_at"],
            "filename": fname,
            "size": f"{fsize_kb} KB",
        })

        logger.info(f"✅ Backup yaratildi: {fname} ({fsize_kb} KB)")
        return fname, fsize_kb, None

    except Exception as e:
        logger.error(f"Backup xatosi: {e}")
        return None, None, str(e)


def restore_backup_from_data(backup_data):
    try:
        if not isinstance(backup_data, dict):
            return False, "Backup formati noto'g'ri."
        if backup_data.get("backup_version") not in {"1.0", "2.0", "safety"}:
            return False, "Backup versiyasi mos emas."

        data = backup_data.get("data")
        if not isinstance(data, dict):
            return False, "Backup ma'lumotlari topilmadi."
        for key in ("users", "admins", "animes", "episodes", "channels"):
            if key in data and not isinstance(data[key], list):
                return False, f"Backupdagi '{key}' bo'limi noto'g'ri."

        safety_fname = local_now().strftime("anibest_safety_%Y-%m-%d_%H-%M.json")
        con_s = db(); c_s = con_s.cursor()
        c_s.execute("SELECT user_id,username,full_name,status,vip_expires,premium_expires,"
                    "coins,ref_code,referred_by,last_bonus,join_date,last_active,blocked,"
                    "notifications_enabled FROM users")
        s_users = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM anime")
        s_animes = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM episodes")
        s_eps = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM admins")
        s_admins = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM channels")
        s_channels = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM autopost_channels")
        s_autopost_channels = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM autopost_settings")
        s_autopost_settings = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM admin_permissions")
        s_admin_permissions = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM spam_log")
        s_spam_log = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM autopost_history")
        s_autopost_history = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM manual_posts")
        s_manual_posts = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM manual_post_deliveries")
        s_manual_post_deliveries = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM media_categories")
        s_media_categories = [dict(r) for r in c_s.fetchall()]
        c_s.execute("SELECT * FROM media_items")
        s_media_items = [dict(r) for r in c_s.fetchall()]
        s_extra_tables = {}
        for table in (
            "favorites", "watch_progress", "watch_history",
            "anime_notifications", "notification_deliveries",
            "anime_view_dedupe", "admin_actions",
            "media_parts", "media_item_categories", "media_favorites",
            "media_watch_progress", "media_watch_history",
            "media_notifications", "media_notification_deliveries",
        ):
            c_s.execute(f"SELECT * FROM {table}")
            s_extra_tables[table] = [dict(r) for r in c_s.fetchall()]
        con_s.close()
        safety_data = {
            "backup_version": "safety",
            "created_at": local_now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": {
                "users": s_users, "admins": s_admins, "animes": s_animes,
                "episodes": s_eps, "channels": s_channels, "spam_log": s_spam_log,
                "admin_permissions": s_admin_permissions,
                "autopost_channels": s_autopost_channels,
                "autopost_settings": s_autopost_settings,
                "autopost_history": s_autopost_history,
                "manual_posts": s_manual_posts,
                "manual_post_deliveries": s_manual_post_deliveries,
                "media_categories": s_media_categories,
                "media_items": s_media_items,
                **s_extra_tables,
            }
        }
        with open(safety_fname, "w", encoding="utf-8") as sf:
            json.dump(safety_data, sf, ensure_ascii=False, indent=2)
        logger.info(f"🔒 Xavfsizlik nusxasi: {safety_fname}")

        con = db(); c = con.cursor()
        c.execute("DELETE FROM episodes")
        c.execute("DELETE FROM anime")
        c.execute("DELETE FROM channels")
        c.execute("DELETE FROM autopost_channels")
        c.execute("DELETE FROM autopost_settings")
        c.execute("DELETE FROM admins")
        c.execute("DELETE FROM admin_permissions")
        c.execute("DELETE FROM users")
        c.execute("DELETE FROM spam_log")
        c.execute("DELETE FROM autopost_history")
        c.execute("DELETE FROM manual_post_deliveries")
        c.execute("DELETE FROM manual_posts")
        # Universal bog'liq jadvallar media_items'dan oldin tozalanadi.
        for table in (
            "media_notification_deliveries", "media_watch_history",
            "media_watch_progress", "media_notifications", "media_favorites",
            "media_item_categories", "media_parts",
        ):
            c.execute(f"DELETE FROM {table}")
        c.execute("DELETE FROM media_items")
        c.execute("DELETE FROM media_categories")
        for table in (
            "favorites", "watch_progress", "watch_history",
            "anime_notifications", "notification_deliveries",
            "anime_view_dedupe", "admin_actions",
        ):
            c.execute(f"DELETE FROM {table}")

        if "users" in data:
            for u in data["users"]:
                c.execute("""
                    INSERT OR REPLACE INTO users
                    (user_id,username,full_name,status,vip_expires,premium_expires,
                     coins,ref_code,referred_by,last_bonus,join_date,last_active,blocked,
                     notifications_enabled)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    u.get("user_id"), u.get("username"), u.get("full_name"),
                    u.get("status","user"), u.get("vip_expires"), u.get("premium_expires"),
                    u.get("coins",0), u.get("ref_code"), u.get("referred_by"),
                    u.get("last_bonus"), u.get("join_date"), u.get("last_active"),
                    u.get("blocked",0), u.get("notifications_enabled", 1)
                ))

        if "admins" in data:
            for a in data["admins"]:
                c.execute("INSERT OR REPLACE INTO admins(user_id,added_by,added_date) VALUES(?,?,?)",
                          (a.get("user_id"), a.get("added_by"), a.get("added_date")))

        if "admin_permissions" in data:
            for p in data["admin_permissions"]:
                permission_keys = [key for key, _ in PERM_LIST]
                columns = ", ".join(["user_id"] + permission_keys)
                placeholders = ", ".join(["?"] * (len(permission_keys) + 1))
                values = [p.get("user_id")] + [p.get(key, 0) for key in permission_keys]
                c.execute(
                    f"INSERT OR REPLACE INTO admin_permissions({columns}) "
                    f"VALUES({placeholders})",
                    values,
                )

        if "animes" in data:
            for a in data["animes"]:
                c.execute("""
                    INSERT OR REPLACE INTO anime
                    (code,title,description,poster_id,genres,season,ova_info,
                     voice,min_status,age_limit,episode_total,trailer_id,trailer_type,
                     views,added_by,added_date)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    a.get("code"), a.get("title"), a.get("description"),
                    a.get("poster_id"), a.get("genres"), a.get("season","1"),
                    a.get("ova_info"), a.get("voice"), a.get("min_status","user"),
                    a.get("age_limit"), a.get("episode_total"), a.get("trailer_id"),
                    a.get("trailer_type"), a.get("views",0), a.get("added_by"),
                    a.get("added_date")
                ))

        if "episodes" in data:
            for e in data["episodes"]:
                c.execute("""
                    INSERT OR REPLACE INTO episodes
                    (anime_code,ep_num,ep_type,file_id,file_type,added_date)
                    VALUES(?,?,?,?,?,?)
                """, (
                    e.get("anime_code"), e.get("ep_num"), e.get("ep_type","season"),
                    e.get("file_id"), e.get("file_type","video"), e.get("added_date")
                ))

        if "media_categories" in data:
            for category in data["media_categories"]:
                c.execute(
                    """INSERT OR REPLACE INTO media_categories
                       (slug,title,icon,sort_order,active)
                       VALUES(?,?,?,?,?)""",
                    (
                        category.get("slug"), category.get("title"),
                        category.get("icon", "🎬"), category.get("sort_order", 0),
                        category.get("active", 1),
                    ),
                )
        # Eski backup formatlarida bu bo'lim bo'lmasligi mumkin.
        seed_media_categories(c)

        if "media_items" in data:
            media_columns = (
                "id", "media_type", "code", "title", "description", "poster_id",
                "main_media_id", "main_media_type", "genres", "season",
                "episode_total", "age_limit", "trailer_id", "trailer_type",
                "voice", "min_status", "views", "added_by", "added_date",
                "legacy_anime_id", "active",
            )
            for media in data["media_items"]:
                c.execute(
                    f"""INSERT OR REPLACE INTO media_items
                        ({','.join(media_columns)})
                        VALUES({','.join('?' for _ in media_columns)})""",
                    [media.get(column) for column in media_columns],
                )

        universal_columns = {
            "media_parts": (
                "id", "media_id", "part_type", "season_number", "part_number",
                "title", "file_id", "file_type", "added_by", "added_date", "active",
            ),
            "media_item_categories": ("media_id", "category_slug", "sort_order"),
            "media_favorites": ("user_id", "media_id", "added_at"),
            "media_watch_progress": (
                "user_id", "media_id", "part_type", "season_number",
                "part_number", "watched_at",
            ),
            "media_watch_history": (
                "id", "user_id", "media_id", "part_type", "season_number",
                "part_number", "watched_at",
            ),
            "media_notifications": ("user_id", "media_id", "enabled", "added_at"),
            "media_notification_deliveries": (
                "user_id", "media_id", "part_type", "season_number",
                "part_number", "sent_at",
            ),
        }
        # media_items va media_categories endi mavjud bo'lgani uchun foreign-key
        # tartibida universal bog'liq yozuvlarni qaytaramiz.
        for table, columns in (
            ("media_item_categories", universal_columns["media_item_categories"]),
            ("media_parts", universal_columns["media_parts"]),
            ("media_favorites", universal_columns["media_favorites"]),
            ("media_watch_progress", universal_columns["media_watch_progress"]),
            ("media_watch_history", universal_columns["media_watch_history"]),
            ("media_notifications", universal_columns["media_notifications"]),
            ("media_notification_deliveries",
             universal_columns["media_notification_deliveries"]),
        ):
            for row in data.get(table, []):
                values = [row.get(column) for column in columns]
                placeholders = ",".join("?" for _ in columns)
                c.execute(
                    f"INSERT OR REPLACE INTO {table}({','.join(columns)}) "
                    f"VALUES({placeholders})",
                    values,
                )

        # Eski backup formatlarida universal layer bo'lmasa ham, tiklangan
        # anime yozuvlari katalogda ko'rinishi kerak.
        for anime in data.get("animes", []):
            if anime.get("code"):
                _mirror_anime_row(c, anime["code"])

        if "channels" in data:
            for ch in data["channels"]:
                c.execute(
                    """INSERT OR REPLACE INTO channels(
                       channel_id,channel_name,channel_url,platform,active
                    ) VALUES(?,?,?,?,?)""",
                    (
                        ch.get("channel_id"), ch.get("channel_name"),
                        ch.get("channel_url"), ch.get("platform", "telegram"),
                        ch.get("active", 1),
                    ),
                )

        if "autopost_channels" in data:
            for ch in data["autopost_channels"]:
                c.execute("""
                    INSERT OR REPLACE INTO autopost_channels(channel_id,channel_name,channel_url,active)
                    VALUES(?,?,?,?)
                """, (ch.get("channel_id"), ch.get("channel_name"), ch.get("channel_url"), ch.get("active",1)))

        if "autopost_settings" in data:
            for s in data["autopost_settings"]:
                c.execute("INSERT OR REPLACE INTO autopost_settings(key,value) VALUES(?,?)",
                          (s.get("key"), s.get("value")))

        if "spam_log" in data:
            for item in data["spam_log"]:
                c.execute("INSERT OR REPLACE INTO spam_log(user_id,last_time,cnt) VALUES(?,?,?)",
                          (item.get("user_id"), item.get("last_time",0), item.get("cnt",0)))

        if "autopost_history" in data:
            for h in data["autopost_history"]:
                c.execute(
                    """INSERT OR REPLACE INTO autopost_history
                    (id,anime_code,anime_title,post_type,season,ep_num,ep_type,
                     channel_id,channel_name,channel_url,posted_by,posted_by_name,
                     posted_at,message_id,status,error,text,media_id,media_type,button_text,
                     genres,voice,min_status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        h.get("id"), h.get("anime_code"), h.get("anime_title"),
                        h.get("post_type"), h.get("season"), h.get("ep_num"),
                        h.get("ep_type"), h.get("channel_id"), h.get("channel_name"),
                        h.get("channel_url"), h.get("posted_by"), h.get("posted_by_name"),
                        h.get("posted_at"), h.get("message_id"), h.get("status"), h.get("error"),
                        h.get("text"), h.get("media_id"), h.get("media_type"),
                        h.get("button_text"), h.get("genres"), h.get("voice"),
                        h.get("min_status"),
                    ),
                )

        if "manual_posts" in data:
            for p in data["manual_posts"]:
                c.execute(
                    """INSERT OR REPLACE INTO manual_posts
                    (id,text,custom_text,post_type,category,image_id,video_id,audio_id,age_limit,
                     anime_title,description,genres,season,episodes,voice,
                     min_status,anime_code,channel_messages,last_posted_at,
                     created_by,created_at,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        p.get("id"), p.get("text") or "", p.get("custom_text"),
                        p.get("post_type") or "new_anime", p.get("category"),
                        p.get("image_id"), p.get("video_id"), p.get("audio_id"),
                        p.get("age_limit"), p.get("anime_title"), p.get("description"),
                        p.get("genres"), p.get("season"), p.get("episodes"),
                        p.get("voice"), p.get("min_status"), p.get("anime_code"),
                        p.get("channel_messages") or "{}", p.get("last_posted_at"),
                        p.get("created_by"), p.get("created_at"),
                        p.get("status", "active"),
                    ),
                )

        if "manual_post_deliveries" in data:
            for delivery in data["manual_post_deliveries"]:
                c.execute(
                    """INSERT OR REPLACE INTO manual_post_deliveries
                    (id,post_id,channel_id,channel_name,message_id,media_type,
                     status,error,posted_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        delivery.get("id"), delivery.get("post_id"),
                        delivery.get("channel_id"), delivery.get("channel_name"),
                        delivery.get("message_id"), delivery.get("media_type"),
                        delivery.get("status", "success"), delivery.get("error"),
                        delivery.get("posted_at"), delivery.get("updated_at"),
                    ),
                )

        extra_columns = {
            "favorites": ("user_id", "anime_code", "added_at"),
            "watch_progress": ("user_id", "anime_code", "ep_type", "ep_num", "watched_at"),
            "watch_history": ("id", "user_id", "anime_code", "ep_type", "ep_num", "watched_at"),
            "anime_notifications": ("user_id", "anime_code", "enabled", "added_at"),
            "notification_deliveries": ("user_id", "anime_code", "ep_type", "ep_num", "sent_at"),
            "anime_view_dedupe": ("user_id", "anime_code", "viewed_date", "viewed_at"),
            "admin_actions": ("id", "admin_id", "action", "anime_code", "ep_type", "ep_num", "created_at"),
        }
        for table, columns in extra_columns.items():
            for row in data.get(table, []):
                placeholders = ",".join("?" for _ in columns)
                values = [row.get(column) for column in columns]
                if table == "watch_progress" and not values[4]:
                    continue
                c.execute(
                    f"INSERT OR REPLACE INTO {table}({','.join(columns)}) "
                    f"VALUES({placeholders})",
                    values,
                )

        con.commit(); con.close()
        logger.info("✅ Backup muvaffaqiyatli tiklandi")
        return True, None

    except Exception as e:
        try: con.rollback(); con.close()
        except (NameError, sqlite3.Error): pass
        logger.error(f"Restore xatosi: {e}")
        return False, str(e)


# ============================================================
#  /start
# ============================================================

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    global BOT_USERNAME
    if not BOT_USERNAME:
        try: BOT_USERNAME = bot.get_me().username or ""
        except Exception: pass

    uid = msg.from_user.id
    args = msg.text.split()
    ref = None
    deep_anime_code = None

    if len(args) > 1:
        param = args[1].strip()
        if param.startswith("r") and param[1:].isdigit():
            ref = int(param[1:])
        elif param:
            if len(param) <= 64 and not param.startswith("/"):
                deep_anime_code = param

    is_new = reg_user(uid, msg.from_user.username, msg.from_user.full_name, ref)

    if not check_sub(uid):
        chs = get_channels()
        if chs:
            if deep_anime_code:
                sset(uid, "pending_deep_link", {"code": deep_anime_code})
                sub_text = (
                    "Botdan foydalanish uchun quyidagi kanallarga *majburiy obuna* bo'ling.\n\n"
                    "Obuna bo'lgach ✅ *Tekshirish* tugmasini bosing."
                )
            else:
                sub_text = (
                    f"🎬 *AniBest Media*\n\n"
                    f"Assalomu alaykum, *{msg.from_user.first_name}*! 👋\n\n"
                    f"Botdan foydalanish uchun quyidagi kanallarga *majburiy obuna* bo'ling:\n\n"
                    f"Obuna bo'lgach ✅ *Tekshirish* tugmasini bosing."
                )
            safe(bot.send_message, msg.chat.id, sub_text, reply_markup=sub_kb())
            return

    if deep_anime_code:
        a = get_anime(deep_anime_code)
        if a:
            show_anime(msg.chat.id, uid, deep_anime_code)
        elif get_media_item(deep_anime_code):
            show_media_item(
                msg.chat.id, uid, get_media_item(deep_anime_code)["id"],
            )
        else:
            kb_back = types.InlineKeyboardMarkup()
            kb_back.add(types.InlineKeyboardButton("🏠 Bosh menyu", callback_data="GO_HOME"))
            safe(bot.send_message, msg.chat.id,
                "❌ *Bunday media topilmadi.*\n\nBosh menyudan qidiring.",
                reply_markup=kb_back)
        return

    # Oddiy /start oqimida effekt alohida xabar bo'lishi kerak.
    # `safe` xato yuz bersa ham quyidagi salomlashuvni to'xtatmaydi.
    safe(bot.send_message, msg.chat.id, "✨")
    txt = (
        f"🎬 *AniBest Media ga xush kelibsiz!*\n\n"
        f"Salom, *{msg.from_user.first_name}*! "
        + ("🎉 Ro'yxatdan o'tdingiz!\n\n" if is_new else "👋 Qayta xush kelibsiz!\n\n") +
        f"🔹 Kodi bilan olish — kontent kodini yozing\n"
        f"🔹 Qidirish — '🔍 Qidirish' tugmasini bosing\n"
        f"🔹 Kunlik bonus — Har kuni +5 tanga\n"
        f"🔹 VIP — 50 tanga to'plang, avtomatik VIP!\n\n"
        f"📡 Kanal: {get_main_channel_tag()}"
    )
    safe(bot.send_message, msg.chat.id, txt, reply_markup=main_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data == "GO_HOME")
def cb_go_home(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    safe(bot.send_message, call.message.chat.id, "🏠 Asosiy menyu", reply_markup=main_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def cb_check_sub(call):
    uid = call.from_user.id
    if check_sub(uid):
        bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi!")
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception: pass
        reg_user(uid, call.from_user.username, call.from_user.full_name)
        pending = sget(uid).get("data", {}) if sget(uid).get("state") == "pending_deep_link" else {}
        deep_code = pending.get("code")
        if deep_code:
            sclear(uid)
            if get_anime(deep_code):
                show_anime(call.message.chat.id, uid, deep_code)
            elif get_media_item(deep_code):
                show_media_item(
                    call.message.chat.id, uid, get_media_item(deep_code)["id"],
                )
            else:
                safe(bot.send_message, call.message.chat.id,
                     "❌ *Bunday media topilmadi.*", reply_markup=main_kb(uid))
            return
        safe(bot.send_message, call.message.chat.id, "✨")
        txt = (
            f"🎬 *AniBest Media ga xush kelibsiz!*\n\n"
            f"Salom, *{call.from_user.first_name}*! 👋\n\n"
            f"🔹 Kodi bilan olish — kontent kodini yozing\n"
            f"🔹 Qidirish — '🔍 Qidirish' tugmasini bosing\n"
            f"🔹 Kunlik bonus — Har kuni +5 tanga\n\n"
            f"📡 Kanal: {get_main_channel_tag()}"
        )
        safe(bot.send_message, call.message.chat.id, txt, reply_markup=main_kb(uid))
    else:
        bot.answer_callback_query(call.id, "❌ Siz hali obuna bo'lmadingiz!", show_alert=True)


# ============================================================
#  PROFILE
# ============================================================

@bot.message_handler(func=lambda m: m.text == "👤 Profilim")
def h_profile(msg):
    uid = msg.from_user.id
    if not require_sub(uid, msg.chat.id): return
    u = get_user(uid)
    if not u:
        safe(bot.send_message, msg.chat.id, "❌ /start ni bosing."); return
    st = get_status(uid)
    con = db(); c = con.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    refs = c.fetchone()[0]; con.close()
    exp = ""
    if st == "vip" and u.get("vip_expires"):
        exp = f"\n⏰ Muddati: {str(u['vip_expires'])[:10]}"
    elif st == "premium" and u.get("premium_expires"):
        exp = f"\n⏰ Muddati: {str(u['premium_expires'])[:10]}"
    txt = (
        f"👤 *MENING PROFILIM*\n\n"
        f"🆔 ID: `{uid}`\n"
        f"📛 Ism: *{u['full_name']}*\n"
        f"{ST_EMOJI.get(st,'👤')} Status: *{ST_NAME.get(st,'Oddiy')}*{exp}\n"
        f"💰 Tanga: *{u['coins']}*\n"
        f"👥 Referallar: *{refs}* kishi\n"
        f"📅 Qo'shilgan: *{str(u['join_date'])[:10]}*\n\n"
        f"🔗 Referal havola:\n`https://t.me/{BOT_USERNAME}?start=r{uid}`"
    )
    safe(bot.send_message, msg.chat.id, txt, reply_markup=_profile_kb(uid))


def _profile_list_keyboard(rows, mode):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        title = (row.get("title") or row.get("anime_code") or "Media")[:42]
        if mode == "favorite":
            callback = f"MED_OPEN|{row['media_id']}" if row.get("media_id") else f"FAVOPEN_{row.get('code') or row.get('anime_code')}"
        else:
            if row.get("media_id"):
                callback = (
                    f"MED_WATCH|{row['media_id']}|{row.get('part_type') or row.get('ep_type', 'part')}"
                    f"|{row.get('season_number') or 1}|{row.get('part_number') or row.get('ep_num')}"
                )
            else:
                callback = f"WATCH_{row.get('code') or row.get('anime_code')}|{row.get('ep_type', 'season')}|{row.get('ep_num')}"
        suffix = ""
        part_number = row.get("part_number") if row.get("part_number") is not None else row.get("ep_num")
        if part_number is not None:
            suffix = f" · {part_number}-bo'lim"
        kb.add(types.InlineKeyboardButton(f"{media_type_icon(row.get('media_type'))} {title}{suffix}", callback_data=callback))
    kb.add(types.InlineKeyboardButton("👤 Profilga qaytish", callback_data="PROFILE_BACK"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data in (
    "PROFILE_FAV", "PROFILE_CONT", "PROFILE_HISTORY", "PROFILE_NOTIF",
    "PROFILE_NOTIF_ON", "PROFILE_NOTIF_OFF", "PROFILE_BACK",
))
def cb_profile_section(call):
    uid = call.from_user.id
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    if call.data == "PROFILE_BACK":
        u = get_user(uid) or {}
        safe(
            bot.send_message,
            call.message.chat.id,
            f"👤 *PROFIL*\n\n🆔 ID: `{uid}`\n📛 Ism: *{u.get('full_name') or '—'}*",
            reply_markup=_profile_kb(uid),
        )
        return
    if call.data == "PROFILE_FAV":
        rows = list_favorites(uid)
        if not rows:
            safe(bot.send_message, call.message.chat.id, "❤️ Hozircha sevimlilar ro'yxati bo'sh.",
                 reply_markup=_profile_kb(uid))
            return
        safe(bot.send_message, call.message.chat.id, "❤️ *SEVIMLILARIM*\n\nAnimeni tanlang:",
             reply_markup=_profile_list_keyboard(rows, "favorite"))
        return
    if call.data == "PROFILE_CONT":
        rows = get_watch_progress(uid)
        if not rows:
            safe(bot.send_message, call.message.chat.id, "🕒 Davom ettirish uchun saqlangan qism yo'q.",
                 reply_markup=_profile_kb(uid))
            return
        safe(bot.send_message, call.message.chat.id, "🕒 *DAVOM ETTIRISH*\n\nQismni tanlang:",
             reply_markup=_profile_list_keyboard(rows, "continue"))
        return
    if call.data == "PROFILE_HISTORY":
        rows = get_watch_history(uid)
        if not rows:
            safe(bot.send_message, call.message.chat.id, "🕓 Ko'rish tarixi hozircha bo'sh.",
                 reply_markup=_profile_kb(uid))
            return
        text = "🕓 *KO'RISH TARIXI*\n\n"
        for row in rows:
            text += (
                f"🎬 *{row.get('title') or row.get('anime_code')}* — "
                f"{row.get('ep_num')}-qism\n"
                f"🕒 {row.get('watched_at')}\n\n"
            )
        safe(bot.send_message, call.message.chat.id, text, reply_markup=_profile_kb(uid))
        return
    if call.data == "PROFILE_NOTIF":
        enabled = bool((get_user(uid) or {}).get("notifications_enabled", 1))
        state = "yoqilgan" if enabled else "o'chirilgan"
        safe(
            bot.send_message,
            call.message.chat.id,
             f"🔔 *BILDIRISHNOMALAR*\n\nUmumiy holat: *{state}*\n"
            "Sevimli yoki kuzatilayotgan media uchun yangi bo'lim qo'shilsa xabar yuboriladi.",
            reply_markup=_profile_kb(uid),
        )
        return
    enabled = call.data == "PROFILE_NOTIF_ON"
    set_global_notifications(uid, enabled)
    safe(
        bot.send_message,
        call.message.chat.id,
         "✅ Barcha media bildirishnomalari yoqildi." if enabled
         else "✅ Barcha media bildirishnomalari o'chirildi.",
        reply_markup=_profile_kb(uid),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("FAVOPEN_"))
def cb_fav_open(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    show_anime(call.message.chat.id, call.from_user.id, call.data[8:])


@bot.callback_query_handler(func=lambda c: c.data in ("RANDOM_ANIME", "RANDOM_MEDIA"))
def cb_random_anime(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    rows, _ = list_media(page=0, per=10000)
    if not rows:
        safe(bot.send_message, call.message.chat.id, "❌ Hozircha media mavjud emas.")
        return
    row = random.choice(rows)
    show_media_item(call.message.chat.id, call.from_user.id, row["id"])


@bot.callback_query_handler(func=lambda c: c.data.startswith("FAV_"))
def cb_favorite(call):
    if not require_sub_cb(call):
        return
    code = call.data[4:]
    if not get_media_item(code):
        bot.answer_callback_query(call.id, "❌ Bu ma'lumot endi mavjud emas.", show_alert=True)
        return
    enabled = toggle_favorite(call.from_user.id, code)
    bot.answer_callback_query(call.id, "✅ Sevimlilarga qo'shildi." if enabled else "✅ Sevimlilardan olib tashlandi.")
    show_anime(call.message.chat.id, call.from_user.id, code)


@bot.callback_query_handler(func=lambda c: c.data.startswith("ANOTIF_"))
def cb_anime_notification(call):
    if not require_sub_cb(call):
        return
    code = call.data[7:]
    if not get_media_item(code):
        bot.answer_callback_query(call.id, "❌ Bu ma'lumot endi mavjud emas.", show_alert=True)
        return
    enabled = toggle_anime_notification(call.from_user.id, code)
    bot.answer_callback_query(call.id, "✅ Bildirishnoma yoqildi." if enabled else "✅ Bildirishnoma o'chirildi.")
    show_anime(call.message.chat.id, call.from_user.id, code)


@bot.callback_query_handler(func=lambda c: c.data.startswith(("FAVM|", "ANOTIFM|")))
def cb_media_preference(call):
    if not require_sub_cb(call):
        return
    try:
        media_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Media havolasi eskirgan.", show_alert=True)
        return
    media = get_media_item_by_id(media_id)
    if not media:
        bot.answer_callback_query(call.id, "❌ Bu media endi mavjud emas.", show_alert=True)
        return
    if call.data.startswith("FAVM|"):
        enabled = toggle_media_favorite(call.from_user.id, media_id)
        message = "✅ Sevimlilarga qo'shildi." if enabled else "✅ Sevimlilardan olib tashlandi."
    else:
        enabled = toggle_media_notification(call.from_user.id, media_id)
        message = "✅ Bildirishnoma yoqildi." if enabled else "✅ Bildirishnoma o'chirildi."
    bot.answer_callback_query(call.id, message)
    show_media_item(call.message.chat.id, call.from_user.id, media_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MED_WATCH|"))
def cb_media_watch_direct(call):
    if not require_sub_cb(call):
        return
    try:
        _, media_id, part_type, season_number, part_number = call.data.split("|", 4)
        media_id, season_number, part_number = int(media_id), int(season_number), int(part_number)
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Media bo'limi havolasi eskirgan.", show_alert=True)
        return
    con = db()
    c = con.cursor()
    c.execute(
        "SELECT * FROM media_parts WHERE media_id=? AND part_type=? AND season_number=? "
        "AND part_number=? AND active=1",
        (media_id, part_type, season_number, part_number),
    )
    row = c.fetchone()
    con.close()
    if not row:
        media = get_media_item_by_id(media_id)
        if media and media.get("main_media_id") and part_number == 1:
            bot.answer_callback_query(call.id)
            record_media_watch(call.from_user.id, media_id, 1, part_type, season_number)
            _send_media_main(call.message.chat.id, media)
            return
        bot.answer_callback_query(call.id, "❌ Bu bo'lim endi mavjud emas.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _send_media_part(call.message.chat.id, dict(row), call.from_user.id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("WATCH_"))
def cb_watch_direct(call):
    if not require_sub_cb(call):
        return
    try:
        code, etype, num = call.data[6:].split("|", 2)
        num = int(num)
    except (ValueError, TypeError):
        bot.answer_callback_query(call.id, "❌ Qism havolasi eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    ep = get_ep(code, num, etype)
    anime = get_anime(code)
    if not ep or not anime:
        safe(bot.send_message, call.message.chat.id, "❌ Bu qism endi mavjud emas.")
        return
    record_watch(call.from_user.id, code, num, etype)
    _send_episode_file(call.message.chat.id, anime, ep, num, etype)


@bot.message_handler(func=lambda m: m.text in ("🎲 Tasodifiy tanlov", "🎲 Tasodifiy media", "🎲 Tasodifiy anime"))
def h_random(msg):
    if not require_sub(msg.from_user.id, msg.chat.id):
        return
    rows, _ = list_media(page=0, per=10000)
    if not rows:
        safe(bot.send_message, msg.chat.id, "❌ Hozircha media mavjud emas.")
        return
    show_media_item(msg.chat.id, msg.from_user.id, random.choice(rows)["id"])


# ============================================================
#  DAILY BONUS
# ============================================================

@bot.message_handler(func=lambda m: m.text == "🎁 Kunlik bonus")
def h_bonus(msg):
    uid = msg.from_user.id
    if not require_sub(uid, msg.chat.id): return
    u = get_user(uid)
    if not u:
        safe(bot.send_message, msg.chat.id, "❌ /start ni bosing."); return
    today = local_today().strftime("%Y-%m-%d")
    con = db(); c = con.cursor()
    c.execute(
        "UPDATE users SET last_bonus=? WHERE user_id=? AND (last_bonus IS NULL OR last_bonus!=?)",
        (today, uid, today),
    )
    rows_changed = c.rowcount
    con.commit(); con.close()
    if rows_changed == 0:
        safe(bot.send_message, msg.chat.id,
            "⏰ *Bugun bonus oldingiz!*\n\nErtaga yana keling 😊\nHar kun +5 tanga bepul!")
        return
    add_coins(uid, 5)
    u2 = get_user(uid)
    coins = u2["coins"] if u2 else "?"
    safe(bot.send_message, msg.chat.id,
        f"🎁 *Kunlik bonus!*\n\n+5 tanga qo'shildi!\n"
        f"💰 Jami: *{coins}* tanga\n\n"
        f"💡 50 tanga to'plasangiz ⭐ VIP avtomatik beriladi!")


# ============================================================
#  REFERRAL
# ============================================================

@bot.message_handler(func=lambda m: m.text == "👥 Referal")
def h_ref(msg):
    uid = msg.from_user.id
    if not require_sub(uid, msg.chat.id): return
    con = db(); c = con.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (uid,))
    refs = c.fetchone()[0]; con.close()
    safe(bot.send_message, msg.chat.id,
        f"👥 *REFERAL TIZIMI*\n\n"
        f"Har bir do'stingiz uchun *+5 tanga* olasiz!\n\n"
        f"👤 Sizning referallaringiz: *{refs}* kishi\n\n"
        f"🔗 *Havolangiz:*\n`https://t.me/{BOT_USERNAME}?start=r{uid}`\n\n"
        f"📤 Havolani do'stlaringizga yuboring!")


# ============================================================
#  SEARCH
# ============================================================

@bot.message_handler(func=lambda m: m.text == "🎬 Anime qidirish")
def h_search_prompt(msg):
    uid = msg.from_user.id
    if not require_sub(uid, msg.chat.id): return
    sset(uid, "searching")
    safe(bot.send_message, msg.chat.id, "🔍 *Qidiruv*\n\nAnime nomi yoki kodini yozing:")


# ============================================================
#  POPULAR / RECENT
# ============================================================

@bot.message_handler(func=lambda m: m.text in ("🔥 Trendda", "🔥 Eng mashhur"))
def h_pop(msg):
    if not require_sub(msg.from_user.id, msg.chat.id): return
    animes, total = ranked_anime("popular", 0)
    if not animes:
        safe(bot.send_message, msg.chat.id, "❌ Hozircha anime yo'q."); return
    safe(
        bot.send_message, msg.chat.id,
        "🔥 *ENG MASHHUR ANIMELER*\n\nAnimeni tanlang:",
        reply_markup=anime_list_keyboard(animes, "popular", 0, total),
    )


@bot.message_handler(func=lambda m: m.text in ("🆕 Yangi qo'shilganlar", "🆕 Yangi qo'shilgan"))
def h_new(msg):
    if not require_sub(msg.from_user.id, msg.chat.id): return
    animes, total = ranked_anime("new", 0)
    if not animes:
        safe(bot.send_message, msg.chat.id, "❌ Hozircha anime yo'q."); return
    safe(
        bot.send_message, msg.chat.id,
        "🆕 *YANGI QO'SHILGAN ANIMELER*\n\nAnimeni tanlang:",
        reply_markup=anime_list_keyboard(animes, "new", 0, total),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("LIST_"))
def cb_ranked_list(call):
    if not require_sub_cb(call):
        return
    try:
        kind, page = call.data[5:].rsplit("_", 1)
        kind = "popular" if kind == "POPULAR" else "new"
        page = int(page)
    except (ValueError, TypeError):
        bot.answer_callback_query(call.id, "❌ Ro'yxat eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    rows, total = ranked_anime(kind, page)
    title = "🔥 *ENG MASHHUR ANIMELER*" if kind == "popular" else "🆕 *YANGI QO'SHILGAN ANIMELER*"
    try:
        bot.edit_message_text(
            f"{title}\n\nAnimeni tanlang:",
            call.message.chat.id, call.message.message_id,
            reply_markup=anime_list_keyboard(rows, kind, page, total),
        )
    except Exception:
        safe(bot.send_message, call.message.chat.id, f"{title}\n\nAnimeni tanlang:",
             reply_markup=anime_list_keyboard(rows, kind, page, total))


@bot.callback_query_handler(func=lambda c: c.data.startswith(("ANID_", "ANSEL_")))
def cb_anime_select(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    if call.data.startswith("ANID_"):
        try:
            anime = get_anime_by_id(int(call.data[5:]))
        except (TypeError, ValueError):
            anime = None
    else:
        anime = get_anime(call.data[6:])
    if not anime:
        safe(bot.send_message, call.message.chat.id, "❌ Bu ma'lumot endi mavjud emas.")
        return
    show_anime(call.message.chat.id, call.from_user.id, anime["code"])


# ============================================================
#  CATEGORIES
# ============================================================

@bot.message_handler(func=lambda m: m.text == "📋 Kategoriyalar")
def h_cats(msg):
    if not require_sub(msg.from_user.id, msg.chat.id): return
    kb = types.InlineKeyboardMarkup(row_width=2)
    for eng, uzb in GENRES:
        kb.add(types.InlineKeyboardButton(
            f"{uzb} — {genre_count(eng)}",
            callback_data=f"CAT_{eng}",
        ))
    safe(bot.send_message, msg.chat.id, "📋 *KATEGORIYALAR*\n\nQaysi janrni ko'rmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("CAT_"))
def cb_cat(call):
    bot.answer_callback_query(call.id)
    if not require_sub_cb(call): return
    genre = call.data[4:]
    animes = anime_by_genre(genre, limit=10, offset=0)
    uname = next((uzb for eng, uzb in GENRES if eng == genre), genre)
    if not animes:
        safe(bot.send_message, call.message.chat.id, f"❌ *{uname}* janrida hozircha anime yo'q."); return
    kb, total, total_pages = category_keyboard(genre, 0)
    txt = f"📁 *{uname}* janridagi animeler:\n📄 Sahifa: 1/{total_pages}\n\nAnimeni tanlang:"
    try:
        bot.edit_message_text(txt, call.message.chat.id, call.message.message_id, reply_markup=kb)
    except Exception:
        safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("CATP|"))
def cb_cat_page(call):
    if not require_sub_cb(call):
        return
    try:
        _, genre, page = call.data.split("|", 2)
        page = int(page)
    except (ValueError, TypeError):
        bot.answer_callback_query(call.id, "❌ Kategoriya sahifasi eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    rows = anime_by_genre(genre, limit=10, offset=page * 10)
    uname = next((uzb for eng, uzb in GENRES if eng == genre), genre)
    if not rows:
        safe(bot.send_message, call.message.chat.id, "❌ Bu sahifada anime yo'q.")
        return
    kb, total, total_pages = category_keyboard(genre, page)
    text = f"📁 *{uname}* janridagi animeler:\n📄 Sahifa: {page + 1}/{total_pages}\n\nAnimeni tanlang:"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb)
    except Exception:
        safe(bot.send_message, call.message.chat.id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "CATS")
def cb_cats(call):
    bot.answer_callback_query(call.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    for eng, uzb in GENRES:
        kb.add(types.InlineKeyboardButton(
            f"{uzb} — {genre_count(eng)}",
            callback_data=f"CAT_{eng}",
        ))
    try:
        bot.edit_message_text("📋 *KATEGORIYALAR*\n\nQaysi janrni ko'rmoqchisiz?",
                              call.message.chat.id, call.message.message_id, reply_markup=kb)
    except Exception:
        safe(bot.send_message, call.message.chat.id,
             "📋 *KATEGORIYALAR*\n\nQaysi janrni ko'rmoqchisiz?", reply_markup=kb)


# ============================================================
#  UNIVERSAL MEDIA KATALOGI
# ============================================================

def _media_categories_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("📚 Barcha media", callback_data="MED_CAT|all|0"))
    for category in get_media_categories():
        kb.add(types.InlineKeyboardButton(
            f"{category['icon']} {category['title']}",
            callback_data=f"MED_CAT|{category['slug']}|0",
        ))
    kb.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="GO_HOME"))
    return kb


def _media_type_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    for media_type in MEDIA_TYPES:
        kb.add(types.InlineKeyboardButton(
            f"{media_type_icon(media_type)} {media_type_label(media_type)}",
            callback_data=f"MEDA_TYPE|{media_type}",
        ))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MEDA_NO"))
    return kb


def _media_status_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("👤 Hammaga", callback_data="MEDA_STATUS|user"),
        types.InlineKeyboardButton("⭐ VIP+", callback_data="MEDA_STATUS|vip"),
        types.InlineKeyboardButton("💎 Premium+", callback_data="MEDA_STATUS|premium"),
    )
    return kb


def _media_next_prompt(chat_id, uid, state, data, prompt):
    sset(uid, state, data)
    safe(bot.send_message, chat_id, prompt)


def _media_form_preview(data):
    return (
        f"✅ *MEDIA TASDIQLASH*\n\n"
        f"🏷️ *Turi:* {media_type_icon(data.get('media_type'))} "
        f"{media_type_label(data.get('media_type'))}\n"
        f"📌 *Kod:* `{data.get('code')}`\n"
        f"🎬 *Nomi:* {data.get('title') or '—'}\n"
        f"📝 *Tavsif:* {data.get('description') or '—'}\n"
        f"🎭 *Janrlar:* {data.get('genres') or '—'}\n"
        f"📺 *Fasl:* {data.get('season') or '—'}\n"
        f"🎞️ *Qismlar:* {data.get('episode_total') or '—'}\n"
        f"🎙️ *Ovoz:* {data.get('voice') or '—'}\n"
        f"🔞 *Yosh:* {format_age_category(data.get('age_limit'))}\n"
        f"🔐 *Kirish:* {ST_NAME.get(data.get('min_status'), 'Oddiy')}\n"
        f"🖼️ *Poster:* {'Bor' if data.get('poster_id') else 'Yo‘q'}\n"
        f"📦 *Asosiy fayl:* {'Bor' if data.get('main_media_id') else 'Yo‘q'}"
    )


def _media_confirm_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Saqlash", callback_data="MEDA_OK"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MEDA_NO"),
    )
    return kb


def _media_list_kb(rows, scope, page, total):
    kb = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        icon = media_type_icon(row.get("media_type"))
        title = (row.get("title") or row.get("code") or "Media")[:42]
        kb.add(types.InlineKeyboardButton(
            f"{icon} {title}",
            callback_data=f"MED_OPEN|{row['id']}",
        ))
    total_pages = max(1, (total + 9) // 10)
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            "⬅️ Oldingi", callback_data=f"MED_PAGE|{scope}|{page - 1}",
        ))
    if page + 1 < total_pages:
        nav.append(types.InlineKeyboardButton(
            "➡️ Keyingi", callback_data=f"MED_PAGE|{scope}|{page + 1}",
        ))
    if nav:
        kb.row(*nav)
    kb.add(types.InlineKeyboardButton("📚 Kategoriyalarga qaytish", callback_data="MED_CATS"))
    return kb


def _media_list_text(scope, rows, page, total):
    if scope == "all":
        heading = "📚 *BARCHA MEDIA*"
    else:
        heading = f"{media_type_icon(scope)} *{media_type_label(scope).upper()}*"
    total_pages = max(1, (total + 9) // 10)
    return f"{heading}\n\n📄 Sahifa: {page + 1}/{total_pages}\n\nMedia tanlang:"


def _show_media_list(chat_id, scope="all", page=0, edit_mid=None):
    rows, total = list_media(None if scope == "all" else scope, page=page)
    if not rows:
        text = "❌ Bu kategoriyada hozircha media yo'q."
        if edit_mid:
            safe_edit(chat_id, edit_mid, text, reply_markup=_media_categories_kb())
        else:
            safe(bot.send_message, chat_id, text, reply_markup=_media_categories_kb())
        return
    text = _media_list_text(scope, rows, page, total)
    kb = _media_list_kb(rows, scope, page, total)
    if edit_mid:
        safe_edit(chat_id, edit_mid, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


def _media_detail_kb(media):
    kb = types.InlineKeyboardMarkup(row_width=1)
    parts = get_media_parts(media["id"])
    if media.get("main_media_id"):
        kb.add(types.InlineKeyboardButton(
            "▶️ Asosiy faylni tomosha qilish",
            callback_data=f"MED_PLAY|{media['id']}",
        ))
    if parts:
        kb.add(types.InlineKeyboardButton(
            f"📁 Qismlar / fayllar ({len(parts)})",
            callback_data=f"MED_PARTS|{media['id']}|all|0",
        ))
    favorite_label = (
        "💔 Sevimlilardan olib tashlash"
        if is_media_favorite(media.get("_viewer_id", 0), media["id"])
        else "❤️ Sevimliga qo'shish"
    )
    notification_label = (
        "🔕 Bildirishnomani o'chirish"
        if media_notifications_enabled(media.get("_viewer_id", 0), media["id"])
        else "🔔 Bildirishnomani yoqish"
    )
    kb.row(
        types.InlineKeyboardButton(
            favorite_label, callback_data=f"FAVM|{media['id']}"
        ),
        types.InlineKeyboardButton(
            notification_label, callback_data=f"ANOTIFM|{media['id']}"
        ),
    )
    username = (BOT_USERNAME or os.environ.get("BOT_USERNAME", "anibestuzbbot")).lstrip("@")
    kb.add(types.InlineKeyboardButton(
        "📤 Ulashish",
        url=f"https://t.me/{username}?start={media['code']}",
    ))
    kb.add(types.InlineKeyboardButton(
        "📚 Kategoriyaga qaytish",
        callback_data=f"MED_CAT|{media['media_type']}|0",
    ))
    kb.add(types.InlineKeyboardButton("🎲 Boshqa media", callback_data="RANDOM_MEDIA"))
    kb.add(types.InlineKeyboardButton("🏠 Asosiy menyu", callback_data="GO_HOME"))
    return kb


def _media_part_keyboard(part):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        "📁 Qismlar / fayllar",
        callback_data=f"MED_PARTS|{part['media_id']}|all|0",
    ))
    kb.add(types.InlineKeyboardButton(
        "🔙 Media ma'lumotiga", callback_data=f"MED_OPEN|{part['media_id']}"
    ))
    return kb


def _send_media_part(chat_id, part, uid=None):
    media = get_media_item_by_id(part["media_id"])
    if not media:
        safe(bot.send_message, chat_id, "❌ Bu media endi mavjud emas.")
        return
    if uid is not None and not can_access(
        get_status(uid), media.get("min_status") or "user"
    ):
        safe(bot.send_message, chat_id, "🔒 Bu media sizning profilingiz uchun yopiq.")
        return
    if uid is not None:
        record_media_watch(
            uid, media["id"], part["part_number"], part.get("part_type") or "part",
            part.get("season_number") or 1,
        )
        if media.get("media_type") == "anime":
            legacy_type = "ova" if part.get("part_type") == "ova" else "season"
            record_watch(uid, media["code"], part["part_number"], legacy_type)
    season = part.get("season_number") or 1
    label = media_part_label(part.get("part_type"))
    caption = (
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n"
        f"📁 *{label}:* {part['part_number']}\n"
        f"📺 *Fasl:* {season}\n"
        f"🎭 *Janrlar:* {media.get('genres') or '—'}\n"
        f"🎙️ *Ovoz:* {media.get('voice') or '—'}\n\n"
        f"📡 *Kanal:* {get_main_channel_tag()}"
    )
    file_id = part["file_id"]
    try:
        if part.get("file_type") == "video":
            bot.send_video(chat_id, file_id, caption=caption,
                           reply_markup=_media_part_keyboard(part))
        elif part.get("file_type") == "animation":
            bot.send_animation(chat_id, file_id, caption=caption,
                               reply_markup=_media_part_keyboard(part))
        elif part.get("file_type") == "audio":
            bot.send_audio(chat_id, file_id, caption=caption,
                           reply_markup=_media_part_keyboard(part))
        elif part.get("file_type") == "voice":
            bot.send_voice(chat_id, file_id, caption=caption,
                           reply_markup=_media_part_keyboard(part))
        elif part.get("file_type") == "photo":
            bot.send_photo(chat_id, file_id, caption=caption,
                           reply_markup=_media_part_keyboard(part))
        else:
            bot.send_document(chat_id, file_id, caption=caption,
                              reply_markup=_media_part_keyboard(part))
    except Exception:
        logger.exception("Media bo'limi yuborilmadi [%s/%s]", media["code"], part["id"])
        safe(bot.send_message, chat_id, "❌ Media faylini yuborishda xato yuz berdi.")


def _show_media_parts(chat_id, uid, media_id, part_type="all", page=0, edit_mid=None):
    media = get_media_item_by_id(media_id)
    if not media:
        safe(bot.send_message, chat_id, "❌ Bu media endi mavjud emas.")
        return
    if not can_access(get_status(uid), media.get("min_status") or "user"):
        safe(bot.send_message, chat_id, "🔒 Bu media sizning profilingiz uchun yopiq.")
        return
    all_parts = get_media_parts(media_id, part_type=part_type)
    per = 10
    total_pages = max(1, (len(all_parts) + per - 1) // per)
    page = max(0, min(int(page), total_pages - 1))
    parts = all_parts[page * per:(page + 1) * per]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for part in parts:
        label = media_part_label(part.get("part_type"))
        kb.add(types.InlineKeyboardButton(
            f"{label} {part.get('part_number')} · S{part.get('season_number') or 1}",
            callback_data=f"MED_PART|{part['id']}",
        ))
    nav = []
    if page > 0:
        nav.append(types.InlineKeyboardButton(
            "⬅️ Oldingi", callback_data=f"MED_PARTS|{media_id}|{part_type}|{page-1}"
        ))
    if page + 1 < total_pages:
        nav.append(types.InlineKeyboardButton(
            "➡️ Keyingi", callback_data=f"MED_PARTS|{media_id}|{part_type}|{page+1}"
        ))
    if nav:
        kb.row(*nav)
    kb.add(types.InlineKeyboardButton(
        "🔙 Media ma'lumotiga", callback_data=f"MED_OPEN|{media_id}"
    ))
    text = (
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n"
        f"📁 *Media qismlari / fayllari*\n\n"
        f"📄 Sahifa: {page + 1}/{total_pages}\n"
        "Kerakli faylni tanlang:"
    )
    if edit_mid:
        safe_edit(chat_id, edit_mid, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


def show_media_item(chat_id, uid, media_id, edit_mid=None):
    try:
        media = get_media_item_by_id(int(media_id))
    except (TypeError, ValueError):
        media = None
    if not media:
        safe(bot.send_message, chat_id, "❌ Bu media endi mavjud emas.")
        return
    status = get_status(uid)
    if not can_access(status, media.get("min_status") or "user"):
        safe(bot.send_message, chat_id, "🔒 Bu media sizning profilingiz uchun yopiq.")
        return
    if inc_media_views(media["id"]):
        media["views"] = int(media.get("views") or 0) + 1
    media["_viewer_id"] = uid
    part_count = len(get_media_parts(media["id"]))
    text = (
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n"
        f"🏷️ *Turi:* {media_type_label(media['media_type'])}\n"
        f"📝 *Tavsif:*\n{media.get('description') or '—'}\n\n"
        f"🎭 *Janrlar:* {media.get('genres') or '—'}\n"
        f"🔞 *Yosh toifasi:* {format_age_category(media.get('age_limit'))}\n"
        f"🎙️ *Ovoz:* {media.get('voice') or '—'}\n"
        f"📁 *Fayllar:* {part_count + (1 if media.get('main_media_id') else 0)} ta\n"
        f"👁 *Ko'rishlar:* {media.get('views') or 0}\n"
    )
    if media.get("season"):
        text += f"📺 *Fasl:* {media['season']}\n"
    if media.get("episode_total"):
        text += f"🎞️ *Qismlar:* {media['episode_total']}\n"
    kb = _media_detail_kb(media)
    if media.get("poster_id"):
        safe(bot.send_photo, chat_id, media["poster_id"], caption=text, reply_markup=kb)
    elif edit_mid:
        safe_edit(chat_id, edit_mid, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


def show_anime(chat_id, uid, code, edit_mid=None):
    """Legacy detail entry point routed through the universal media catalog."""
    media = get_media_item(code)
    if media:
        show_media_item(chat_id, uid, media["id"], edit_mid=edit_mid)
        return
    safe(bot.send_message, chat_id, "❌ Bu media endi mavjud emas.")


def _send_media_main(chat_id, media):
    media_id = media.get("main_media_id")
    media_type = media.get("main_media_type")
    if not media_id:
        safe(bot.send_message, chat_id, "❌ Bu media fayli hali qo'shilmagan.")
        return
    caption = f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n📡 {get_main_channel_tag()}"
    try:
        if media_type == "video":
            bot.send_video(chat_id, media_id, caption=caption)
        elif media_type == "animation":
            bot.send_animation(chat_id, media_id, caption=caption)
        elif media_type == "audio":
            bot.send_audio(chat_id, media_id, caption=caption)
        elif media_type == "voice":
            bot.send_voice(chat_id, media_id, caption=caption)
        elif media_type == "photo":
            bot.send_photo(chat_id, media_id, caption=caption)
        else:
            bot.send_document(chat_id, media_id, caption=caption)
    except Exception:
        logger.exception("Universal media fayli yuborilmadi [%s]", media.get("code"))
        safe(bot.send_message, chat_id, "❌ Media faylini yuborishda xato yuz berdi.")


@bot.message_handler(func=lambda m: m.text in ("📚 Kategoriyalar", "📚 Media kategoriyalari"))
def h_media_categories(msg):
    if not require_sub(msg.from_user.id, msg.chat.id):
        return
    safe(
        bot.send_message, msg.chat.id,
        "📚 *MEDIA KATEGORIYALARI*\n\nKerakli bo'limni tanlang:",
        reply_markup=_media_categories_kb(),
    )


@bot.message_handler(func=lambda m: m.text in ("🔍 Qidirish", "🔍 Media qidirish"))
def h_media_search_prompt(msg):
    if not require_sub(msg.from_user.id, msg.chat.id):
        return
    sset(msg.from_user.id, "media_searching")
    safe(bot.send_message, msg.chat.id, "🔍 Media nomi, kodi yoki janrini yozing:")


@bot.message_handler(func=lambda m: m.text in ("📚 Kutubxona", "🎞️ Media katalogi") and is_admin(m.from_user.id))
def h_media_catalog(msg):
    uid = msg.from_user.id
    if not admin_has_perm(uid, "add_media"):
        safe(bot.send_message, msg.chat.id, "❌ Media katalogini ko'rish ruxsati yo'q.")
        return
    lines = ["🎞️ *MEDIA KATALOGI*\n"]
    for category in get_media_categories():
        _, total = list_media(category["slug"], per=1)
        lines.append(f"{category['icon']} {category['title']}: *{total}* ta")
    safe(bot.send_message, msg.chat.id, "\n".join(lines), reply_markup=admin_kb(uid))


@bot.message_handler(func=lambda m: m.text in ("➕ Kontent qo'shish", "➕ Add Media", "➕ Media qo'shish") and is_admin(m.from_user.id))
def h_add_media(msg):
    uid = msg.from_user.id
    if not admin_has_perm(uid, "add_media"):
        safe(bot.send_message, msg.chat.id, "❌ Sizda media qo'shish ruxsati yo'q.")
        return
    sset(uid, "media_type_wait")
    safe(
        bot.send_message, msg.chat.id,
        "➕ *MEDIA QO'SHISH*\n\nMedia turini tanlang:",
        reply_markup=_media_type_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDA_TYPE|"))
def cb_media_type(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_has_perm(uid, "add_media"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    if sget(uid).get("state") != "media_type_wait":
        bot.answer_callback_query(call.id, "❌ Media sessiyasi tugagan.", show_alert=True)
        return
    media_type = call.data.split("|", 1)[1]
    if media_type not in MEDIA_TYPES:
        bot.answer_callback_query(call.id, "❌ Media turi noto'g'ri.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    data = {"media_type": media_type}
    sset(uid, "media_poster_wait", data)
    safe_edit(
        call.message.chat.id, call.message.message_id,
        f"{media_type_icon(media_type)} *{media_type_label(media_type)} qo'shish*\n\n"
        "1️⃣ Poster rasmini yuboring yoki `/skip` yozing:",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDA_STATUS|"))
def cb_media_status(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_has_perm(uid, "add_media"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    si = sget(uid)
    if si.get("state") != "media_status_wait":
        bot.answer_callback_query(call.id, "❌ Media sessiyasi tugagan.", show_alert=True)
        return
    status = call.data.split("|", 1)[1]
    if status not in ST_ORDER:
        bot.answer_callback_query(call.id, "❌ Kirish darajasi noto'g'ri.", show_alert=True)
        return
    data = dict(si.get("data") or {})
    data["min_status"] = status
    bot.answer_callback_query(call.id)
    sset(uid, "media_age_wait", data)
    safe_edit(
        call.message.chat.id, call.message.message_id,
        "9️⃣ Yosh cheklovini yozing (masalan: 16+) yoki `/skip` bosing:",
    )


@bot.callback_query_handler(func=lambda c: c.data in ("MEDA_OK", "MEDA_NO"))
def cb_media_confirm(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_has_perm(uid, "add_media"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    if call.data == "MEDA_NO":
        bot.answer_callback_query(call.id, "Bekor qilindi")
        sclear(uid)
        safe_edit(call.message.chat.id, call.message.message_id, "❌ Media qo'shish bekor qilindi.")
        return
    si = sget(uid)
    if si.get("state") != "media_confirm_wait":
        bot.answer_callback_query(call.id, "❌ Media sessiyasi tugagan.", show_alert=True)
        return
    data = dict(si.get("data") or {})
    title = (data.get("title") or "").strip()
    if not title:
        bot.answer_callback_query(call.id, "❌ Media nomi majburiy.", show_alert=True)
        return
    code = next_content_code()
    data["code"] = code
    media_args = (
        data.get("media_type"), code, title, data.get("description"),
        data.get("poster_id"), data.get("main_media_id"),
        data.get("main_media_type"), data.get("genres"), data.get("season"),
        data.get("episode_total"), data.get("age_limit"), data.get("trailer_id"),
        data.get("trailer_type"), data.get("voice"),
        data.get("min_status", "user"), uid,
    )
    ok = add_media_item(*media_args)
    if not ok:
        # Boshqa admin shu vaqtda kontent qo'shgan bo'lsa, navbatdagi kodni
        # qayta olib bir marta xavfsiz takrorlaymiz.
        code = next_content_code()
        data["code"] = code
        ok = add_media_item(
            data.get("media_type"), code, title, data.get("description"),
            data.get("poster_id"), data.get("main_media_id"),
            data.get("main_media_type"), data.get("genres"), data.get("season"),
            data.get("episode_total"), data.get("age_limit"), data.get("trailer_id"),
            data.get("trailer_type"), data.get("voice"),
            data.get("min_status", "user"), uid,
        )
    if not ok:
        bot.answer_callback_query(call.id, "❌ Kod mavjud yoki ma'lumot noto'g'ri.", show_alert=True)
        return
    bot.answer_callback_query(call.id, "✅ Saqlandi")
    sclear(uid)
    log_admin_action(uid, "media_added", code)
    safe_edit(
        call.message.chat.id, call.message.message_id,
        f"✅ *{media_type_label(data.get('media_type'))} muvaffaqiyatli qo'shildi!*\n\n"
        f"📌 Kod: `{code}`\n🎬 Nomi: *{title}*",
    )
    safe(bot.send_message, call.message.chat.id, "⚙️ Admin panelga qaytildi.", reply_markup=admin_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data in ("MED_CATS",))
def cb_media_categories(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    safe_edit(
        call.message.chat.id, call.message.message_id,
        "📚 *MEDIA KATEGORIYALARI*\n\nKerakli bo'limni tanlang:",
        reply_markup=_media_categories_kb(),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith(("MED_CAT|", "MED_PAGE|")))
def cb_media_list(call):
    if not require_sub_cb(call):
        return
    try:
        parts = call.data.split("|")
        scope = parts[1]
        page = int(parts[2])
        if scope != "all" and scope not in MEDIA_TYPES:
            raise ValueError
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "❌ Kategoriya havolasi eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _show_media_list(call.message.chat.id, scope, page, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MED_OPEN|"))
def cb_media_open(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    show_media_item(call.message.chat.id, call.from_user.id, call.data.split("|", 1)[1])


@bot.callback_query_handler(func=lambda c: c.data.startswith("MED_PLAY|"))
def cb_media_play(call):
    if not require_sub_cb(call):
        return
    bot.answer_callback_query(call.id)
    try:
        media = get_media_item_by_id(int(call.data.split("|", 1)[1]))
    except (TypeError, ValueError):
        media = None
    if not media:
        safe(bot.send_message, call.message.chat.id, "❌ Bu media endi mavjud emas.")
        return
    if not can_access(get_status(call.from_user.id), media.get("min_status") or "user"):
        safe(bot.send_message, call.message.chat.id, "🔒 Bu media sizning profilingiz uchun yopiq.")
        return
    record_media_watch(
        call.from_user.id,
        media["id"],
        1,
        "movie" if media.get("media_type") == "movie" else "part",
        1,
    )
    _send_media_main(call.message.chat.id, media)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MED_PARTS|"))
def cb_media_parts(call):
    if not require_sub_cb(call):
        return
    try:
        _, media_id, part_type, page = call.data.split("|", 3)
        media_id, page = int(media_id), int(page)
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Qismlar havolasi eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _show_media_parts(
        call.message.chat.id, call.from_user.id, media_id, part_type, page,
        edit_mid=call.message.message_id,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MED_PART|"))
def cb_media_part(call):
    if not require_sub_cb(call):
        return
    try:
        part_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Fayl havolasi eskirgan.", show_alert=True)
        return
    part = get_media_part(part_id)
    if not part:
        bot.answer_callback_query(call.id, "❌ Bu fayl endi mavjud emas.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _send_media_part(call.message.chat.id, part, call.from_user.id)


def _media_admin_lookup(value):
    value = (value or "").strip()
    media = get_media_item(value)
    if media:
        return media
    matches = search_media(value, limit=2)
    return matches[0] if len(matches) == 1 else None


def _media_admin_parts_kb(media):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        "➕ Bo'lim/fayl qo'shish", callback_data=f"MEDADM_ADD|{media['id']}"
    ))
    kb.add(types.InlineKeyboardButton(
        "📋 Mavjud bo'limlarni boshqarish", callback_data=f"MEDADM_LIST|{media['id']}"
    ))
    kb.add(types.InlineKeyboardButton("⚙️ Admin panel", callback_data="MEDADM_BACK"))
    return kb


def _media_admin_parts_text(media):
    parts = get_media_parts(media["id"])
    return (
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n"
        f"📌 Kod: `{media['code']}`\n"
        f"📁 Faol bo'lim/fayllar: *{len(parts)}* ta\n\n"
        "Qo'shish yoki mavjud fayllarni boshqarishni tanlang."
    )


def _media_admin_part_types_kb(media_id):
    media = get_media_item_by_id(media_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    for part_type in media_part_types(media):
        kb.add(types.InlineKeyboardButton(
            f"📁 {media_part_label(part_type)}",
            callback_data=f"MEDADM_TYPE|{media_id}|{part_type}",
        ))
    kb.add(types.InlineKeyboardButton(
        "🔙 Media bo'limlariga", callback_data=f"MEDADM_OPEN|{media_id}"
    ))
    return kb


def _media_admin_part_list(chat_id, media_id, edit_mid=None):
    media = get_media_item_by_id(media_id)
    if not media:
        safe(bot.send_message, chat_id, "❌ Media topilmadi.")
        return
    parts = get_media_parts(media_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for part in parts:
        label = (
            f"{media_part_label(part.get('part_type'))} "
            f"{part.get('part_number')} · S{part.get('season_number') or 1}"
        )
        kb.add(types.InlineKeyboardButton(
            f"🗑️ {label}", callback_data=f"MEDADM_DEL|{part['id']}"
        ))
    kb.add(types.InlineKeyboardButton(
        "➕ Yangi bo'lim/fayl", callback_data=f"MEDADM_ADD|{media_id}"
    ))
    kb.add(types.InlineKeyboardButton(
        "🔙 Media bo'limlariga", callback_data=f"MEDADM_OPEN|{media_id}"
    ))
    text = (
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n"
        "📋 O'chirish uchun bo'limni tanlang:"
        if parts else
        f"{media_type_icon(media['media_type'])} *{media['title']}*\n\n"
        "📋 Hozircha qo'shilgan bo'lim/fayl yo'q."
    )
    if edit_mid:
        safe_edit(chat_id, edit_mid, text, reply_markup=kb)
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_OPEN|"))
def cb_media_admin_open(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        media_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Media havolasi eskirgan.", show_alert=True)
        return
    media = get_media_item_by_id(media_id)
    if not media:
        bot.answer_callback_query(call.id, "❌ Media topilmadi.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    safe_edit(
        call.message.chat.id, call.message.message_id,
        _media_admin_parts_text(media), reply_markup=_media_admin_parts_kb(media),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_ADD|"))
def cb_media_admin_add(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        media_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Media havolasi eskirgan.", show_alert=True)
        return
    media = get_media_item_by_id(media_id)
    if not media:
        bot.answer_callback_query(call.id, "❌ Media topilmadi.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    sset(uid, "media_part_type_wait", {"media_id": media_id})
    safe_edit(
        call.message.chat.id, call.message.message_id,
        f"➕ *{media['title']}* uchun bo'lim turini tanlang:",
        reply_markup=_media_admin_part_types_kb(media_id),
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_TYPE|"))
def cb_media_admin_type(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        _, media_id, part_type = call.data.split("|", 2)
        media_id = int(media_id)
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Bo'lim turi eskirgan.", show_alert=True)
        return
    if sget(uid).get("state") != "media_part_type_wait":
        bot.answer_callback_query(call.id, "❌ Media sessiyasi tugagan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    sset(uid, "media_part_season_wait", {
        "media_id": media_id, "part_type": part_type,
    })
    safe_edit(
        call.message.chat.id, call.message.message_id,
        "📺 Fasl/sezon raqamini yuboring yoki standart 1 uchun `/skip` bosing:",
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_LIST|"))
def cb_media_admin_list(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        media_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Media havolasi eskirgan.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _media_admin_part_list(call.message.chat.id, media_id, call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_DEL|"))
def cb_media_admin_delete(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        part_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Fayl havolasi eskirgan.", show_alert=True)
        return
    part = get_media_part(part_id)
    if not part:
        bot.answer_callback_query(call.id, "❌ Bu fayl topilmadi.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Ha", callback_data=f"MEDADM_DELYES|{part_id}"),
        types.InlineKeyboardButton("❌ Yo'q", callback_data=f"MEDADM_LIST|{part['media_id']}"),
    )
    safe(
        bot.send_message, call.message.chat.id,
        f"⚠️ *{part['title'] or media_part_label(part['part_type'])} "
        f"{part['part_number']}* faylini o'chirishni tasdiqlaysizmi?",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDADM_DELYES|"))
def cb_media_admin_delete_yes(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "parts"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    try:
        part_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Fayl havolasi eskirgan.", show_alert=True)
        return
    part = get_media_part(part_id)
    if not part:
        bot.answer_callback_query(call.id, "❌ Bu fayl topilmadi.", show_alert=True)
        return
    if part.get("media_type") == "anime" and part.get("part_type") in {"episode", "ova"}:
        deleted = del_ep(
            part["code"], part["part_number"],
            "ova" if part["part_type"] == "ova" else "season",
        )
    else:
        deleted = delete_media_part(part_id)
    bot.answer_callback_query(call.id, "✅ O'chirildi." if deleted else "❌ O'chirilmadi.")
    log_admin_action(uid, "media_part_deleted", part.get("code"))
    _media_admin_part_list(call.message.chat.id, part["media_id"])


@bot.callback_query_handler(func=lambda c: c.data == "MEDADM_BACK")
def cb_media_admin_back(call):
    bot.answer_callback_query(call.id)
    sclear(call.from_user.id)
    safe(bot.send_message, call.message.chat.id, "⚙️ Admin panel", reply_markup=admin_kb(call.from_user.id))


MEDIA_EDIT_FIELDS = {
    "title": "🎬 Nom",
    "description": "📝 Tavsif",
    "genres": "🎭 Janrlar",
    "season": "📺 Fasl",
    "episode_total": "📁 Bo'limlar soni",
    "voice": "🎙️ Ovoz/dublyaj",
    "age_limit": "🔞 Yosh cheklovi",
    "poster_id": "🖼️ Poster",
    "main_media_id": "📦 Asosiy fayl",
    "min_status": "🔐 Kirish darajasi",
}


def _media_edit_text(draft):
    return (
        f"✏️ *MEDIA TAHRIRLASH*\n\n"
        f"{media_type_icon(draft.get('media_type'))} *{draft.get('title') or '—'}*\n"
        f"📌 Kod: `{draft.get('code')}`\n"
        f"📝 Tavsif: {draft.get('description') or '—'}\n"
        f"🎭 Janrlar: {draft.get('genres') or '—'}\n"
        f"📺 Fasl: {draft.get('season') or '—'}\n"
        f"🎙️ Ovoz: {draft.get('voice') or '—'}\n"
        f"🔞 Yosh: {format_age_category(draft.get('age_limit'))}\n"
        f"🔐 Kirish: {ST_NAME.get(draft.get('min_status') or 'user', 'Oddiy')}\n"
        f"🖼️ Poster: {'bor' if draft.get('poster_id') else 'yo‘q'}\n"
        f"📦 Asosiy fayl: {'bor' if draft.get('main_media_id') else 'yo‘q'}"
    )


def _media_file_from_message(msg):
    fields = {
        "photo": (getattr(msg, "photo", None), "photo"),
        "video": (getattr(msg, "video", None), "video"),
        "animation": (getattr(msg, "animation", None), "animation"),
        "document": (getattr(msg, "document", None), "document"),
        "audio": (getattr(msg, "audio", None), "audio"),
        "voice": (getattr(msg, "voice", None), "voice"),
    }
    value, file_type = fields.get(msg.content_type, (None, None))
    if not value:
        return None, None
    return (
        value[-1].file_id if file_type == "photo" else value.file_id,
        file_type,
    )


def _media_edit_kb():
    kb = types.InlineKeyboardMarkup(row_width=2)
    for field, label in MEDIA_EDIT_FIELDS.items():
        kb.add(types.InlineKeyboardButton(label, callback_data=f"MEDEDIT_FIELD|{field}"))
    kb.add(
        types.InlineKeyboardButton("💾 Saqlash", callback_data="MEDEDIT_SAVE"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MEDEDIT_CANCEL"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDEDIT_FIELD|"))
def cb_media_edit_field(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "edit"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    field = call.data.split("|", 1)[1]
    si = sget(uid)
    if si.get("state") != "media_edit_menu" or field not in MEDIA_EDIT_FIELDS:
        bot.answer_callback_query(call.id, "❌ Tahrirlash sessiyasi tugagan.", show_alert=True)
        return
    draft = dict(si.get("data") or {})
    bot.answer_callback_query(call.id)
    if field == "min_status":
        kb = types.InlineKeyboardMarkup(row_width=3)
        for status in ("user", "vip", "premium"):
            kb.add(types.InlineKeyboardButton(
                ST_NAME[status], callback_data=f"MEDEDIT_STATUS|{status}"
            ))
        kb.add(types.InlineKeyboardButton("⏭️ O'zgarishsiz", callback_data="MEDEDIT_SKIP|min_status"))
        safe(bot.send_message, call.message.chat.id, "🔐 Kirish darajasini tanlang:", reply_markup=kb)
        return
    if field in {"poster_id", "main_media_id"}:
        prompt = "🖼️ Yangi poster yuboring:" if field == "poster_id" else "📦 Yangi asosiy faylni yuboring:"
    else:
        prompt = f"{MEDIA_EDIT_FIELDS[field]} uchun yangi qiymatni yuboring:"
    sset(uid, "media_edit_field", {"draft": draft, "field": field})
    safe(bot.send_message, call.message.chat.id, prompt)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDEDIT_STATUS|"))
def cb_media_edit_status(call):
    uid = call.from_user.id
    si = sget(uid)
    if not is_admin(uid) or si.get("state") != "media_edit_menu":
        bot.answer_callback_query(call.id, "❌ Tahrirlash sessiyasi tugagan.", show_alert=True)
        return
    status = call.data.split("|", 1)[1]
    if status not in ST_ORDER:
        bot.answer_callback_query(call.id, "❌ Holat noto'g'ri.", show_alert=True)
        return
    draft = dict(si.get("data") or {})
    draft["min_status"] = status
    sset(uid, "media_edit_menu", draft)
    bot.answer_callback_query(call.id, "✅ Draft yangilandi.")
    safe(bot.send_message, call.message.chat.id, _media_edit_text(draft), reply_markup=_media_edit_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("MEDEDIT_SKIP|"))
def cb_media_edit_skip(call):
    uid = call.from_user.id
    si = sget(uid)
    if not is_admin(uid) or si.get("state") not in {"media_edit_field", "media_edit_menu"}:
        bot.answer_callback_query(call.id, "❌ Tahrirlash sessiyasi tugagan.", show_alert=True)
        return
    draft = dict((si.get("data") or {}).get("draft") or {}) if si.get("state") == "media_edit_field" else dict(si.get("data") or {})
    sset(uid, "media_edit_menu", draft)
    bot.answer_callback_query(call.id)
    safe(bot.send_message, call.message.chat.id, _media_edit_text(draft), reply_markup=_media_edit_kb())


@bot.callback_query_handler(func=lambda c: c.data in ("MEDEDIT_SAVE", "MEDEDIT_CANCEL"))
def cb_media_edit_action(call):
    uid = call.from_user.id
    si = sget(uid)
    if not is_admin(uid) or si.get("state") not in {"media_edit_menu", "media_edit_field"}:
        bot.answer_callback_query(call.id, "❌ Tahrirlash sessiyasi tugagan.", show_alert=True)
        return
    if call.data == "MEDEDIT_CANCEL":
        sclear(uid)
        bot.answer_callback_query(call.id, "Bekor qilindi")
        safe(bot.send_message, call.message.chat.id, "❌ Media draft bekor qilindi.", reply_markup=admin_kb(uid))
        return
    draft = dict(si.get("data") or {})
    if si.get("state") == "media_edit_field":
        draft = dict(draft.get("draft") or {})
    updates = {
        key: draft.get(key) for key in MEDIA_EDIT_FIELDS
        if key not in {"poster_id", "main_media_id"} or draft.get(key) is not None
    }
    updates.pop("main_media_id", None) if draft.get("main_media_id") is None else None
    updates.pop("poster_id", None) if draft.get("poster_id") is None else None
    ok = update_media(draft.get("code"), **updates)
    if ok:
        log_admin_action(uid, "media_edited", draft.get("code"))
        sclear(uid)
        bot.answer_callback_query(call.id, "✅ Saqlandi")
        safe(bot.send_message, call.message.chat.id, "✅ Media ma'lumotlari saqlandi.", reply_markup=admin_kb(uid))
    else:
        bot.answer_callback_query(call.id, "❌ Saqlashda xato.", show_alert=True)

# ============================================================
#  SPECIAL ANIME
# ============================================================

@bot.message_handler(func=lambda m: m.text in ("💎 Premium", "💎 Maxsus media", "💎 Maxsus animeler"))
def h_special(msg):
    uid = msg.from_user.id
    if not require_sub(uid, msg.chat.id): return
    st = get_status(uid)
    con = db(); c = con.cursor()
    if st in ("premium", "owner", "admin"):
        c.execute("SELECT code,title,min_status FROM anime WHERE min_status IN ('vip','premium')")
    else:
        c.execute("SELECT code,title,min_status FROM anime WHERE min_status='vip'")
    rows = [dict(r) for r in c.fetchall()]; con.close()
    if not rows:
        safe(bot.send_message, msg.chat.id, "❌ Hozircha maxsus media yo'q."); return
    txt = "💎 *MAXSUS MEDIA*\n\n"
    for r in rows:
        ico = "⭐" if r["min_status"] == "vip" else "💎"
        txt += f"{ico} *{r['title']}* | Kod: `{r['code']}`\n"
    safe(bot.send_message, msg.chat.id, txt)


# ============================================================
#  HELP
# ============================================================

@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def h_help(msg):
    if not require_sub(msg.from_user.id, msg.chat.id): return
    safe(bot.send_message, msg.chat.id,
        "ℹ️ *YORDAM*\n\n"
        "🎬 Anime kodi yozing — anime olish\n"
        "🔍 Anime qidirish — nom bo'yicha qidirish\n"
        "📋 Kategoriyalar — janr bo'yicha\n"
        "🔥 Eng mashhur — top animeler\n"
        "🆕 Yangi qo'shilgan — oxirgi animeler\n"
        "👤 Profilim — ma'lumotlaringiz\n"
        "🎁 Kunlik bonus — +5 tanga har kuni\n"
        "👥 Referal — do'st taklif qilish (+5 tanga)\n"
        "⭐ VIP — 50 tanga to'plang, avtomatik VIP!\n\n"
        f"📡 Kanal: {get_main_channel_tag()}\n"
        "💬 Admin: @nowloss")


# ============================================================
#  ADMIN PANEL
# ============================================================

@bot.message_handler(func=lambda m: m.text == "⚙️ Admin panel")
def h_admin(msg):
    uid = msg.from_user.id
    if not is_admin(uid):
        safe(bot.send_message, msg.chat.id, "❌ Ruxsat yo'q!"); return
    safe(bot.send_message, msg.chat.id, "⚙️ *ADMIN PANEL*\n\nXush kelibsiz!", reply_markup=admin_kb(uid))


@bot.message_handler(func=lambda m: m.text == "🔙 Orqaga")
def h_back(msg):
    sclear(msg.from_user.id)
    safe(bot.send_message, msg.chat.id, "🏠 Asosiy menyu", reply_markup=main_kb(msg.from_user.id))


@bot.message_handler(func=lambda m: m.text in ("📡 Avtoposting", "📡 Media avtoposti", "📡 Anime avtoposti") and is_admin(m.from_user.id))
def h_existing_anime_autopost(msg):
    uid = msg.from_user.id
    if not _can_use_autopost(uid):
        safe(bot.send_message, msg.chat.id, "❌ Sizda avtopost ruxsati yo'q.")
        return
    sset(uid, "ap_existing_code_wait")
    safe(
        bot.send_message,
        msg.chat.id,
        "📡 Mavjud media avtoposti\n\nMedia kodini yuboring:",
    )


@bot.message_handler(commands=["cancel"])
def h_cancel(msg):
    sclear(msg.from_user.id)
    safe(bot.send_message, msg.chat.id, "❌ Bekor qilindi.", reply_markup=main_kb(msg.from_user.id))


# ============================================================
#  MAVJUD ANIME AVTOPOSTI
# ============================================================

def _start_existing_anime_autopost(msg, code):
    """Mavjud anime yoki universal media uchun mustaqil post nusxasini tayyorlaydi."""
    uid = msg.from_user.id
    media = get_media_item(code)
    if not media:
        safe(bot.send_message, msg.chat.id, "❌ Bunday media topilmadi. Kodini tekshiring.")
        return
    active_chs = get_autopost_channels(only_active=True)
    if not active_chs:
        sclear(uid)
        safe(bot.send_message, msg.chat.id, "❌ Faol avtopost kanallari yo'q.", reply_markup=admin_kb(uid))
        return
    sset(uid, "ap_existing_wait", {
        "anime_code": media["code"],
        "media_code": media["code"],
        "media_catalog_type": media.get("media_type"),
        "anime_title": media["title"],
        "post_type": "existing_anime",
        "genres": media.get("genres"),
        "voice": media.get("voice"),
        "min_status": media.get("min_status"),
    })
    safe(
        bot.send_message,
        msg.chat.id,
        f"✅ *{media['title']}* avtopostga tayyor.\n\n"
        "Media katalogidagi asl ma'lumotlar o'zgarmaydi.\n"
        "Postni kanalga yuborishdan oldin preview yoki tahrirlashni tanlang.",
        reply_markup=_autopost_offer_kb(len(active_chs)),
    )


@bot.message_handler(commands=["skip"])
def h_skip(msg):
    uid = msg.from_user.id
    si = sget(uid); st = si.get("state", "")
    if st == "media_poster_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["poster_id"] = None
        sset(uid, "media_description_wait", d)
        safe(bot.send_message, msg.chat.id, "2️⃣ Media tavsifini yozing yoki `/skip` bosing:")
    elif st == "media_description_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["description"] = None
        sset(uid, "media_genres_wait", d)
        safe(bot.send_message, msg.chat.id, "3️⃣ Janr yoki tasnifni yozing yoki `/skip` bosing:")
    elif st == "media_genres_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["genres"] = None
        sset(uid, "media_season_wait", d)
        safe(bot.send_message, msg.chat.id, "4️⃣ Fasl ma'lumotini yozing yoki `/skip` bosing:")
    elif st == "media_season_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["season"] = None
        sset(uid, "media_episode_wait", d)
        safe(bot.send_message, msg.chat.id, "5️⃣ Qismlar sonini yozing yoki `/skip` bosing:")
    elif st in ("media_episode_wait", "media_episodes_wait") and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["episode_total"] = None
        sset(uid, "media_voice_wait", d)
        safe(bot.send_message, msg.chat.id, "6️⃣ Ovoz/dublyajni yozing yoki `/skip` bosing:")
    elif st == "media_voice_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["voice"] = None
        sset(uid, "media_status_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            "7️⃣ Media uchun kirish darajasini tanlang:",
            reply_markup=_media_status_kb(),
        )
    elif st == "media_age_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["age_limit"] = None
        sset(uid, "media_main_media_wait", d)
        safe(bot.send_message, msg.chat.id, "🔟 Asosiy media faylini yuboring yoki `/skip` bosing:")
    elif st in ("media_main_media_wait", "media_main_wait") and is_admin(uid) and admin_has_perm(uid, "add_media"):
        d = dict(si.get("data") or {})
        d["main_media_id"] = None
        d["main_media_type"] = None
        d["code"] = next_content_code()
        sset(uid, "media_title_wait", d)
        safe(
            bot.send_message,
            msg.chat.id,
            f"🔢 Avtomatik kod: `{d['code']}`\n"
            "1️⃣1️⃣ Media nomini yozing:",
        )
    elif st == "media_part_season_wait" and is_admin(uid) and admin_media_perm(uid, "parts"):
        d = dict(si.get("data") or {})
        d["season_number"] = 1
        sset(uid, "media_part_number_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            "🔢 Bo'lim raqamini yuboring yoki `/skip` bosing:",
        )
    elif st == "media_part_number_wait" and is_admin(uid) and admin_media_perm(uid, "parts"):
        d = dict(si.get("data") or {})
        d["part_number"] = next_media_part_number(
            d["media_id"], d.get("part_type") or "part", d.get("season_number") or 1,
        )
        sset(uid, "media_part_file_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            f"📦 {d['part_number']}-bo'lim faylini yuboring:\n"
            "Video, GIF, audio, voice, rasm yoki document qabul qilinadi.",
        )


# ============================================================
#  ADMIN: QISM SOZLAMALARI
# ============================================================

@bot.message_handler(func=lambda m: m.text == "🎬 Qismlar boshqaruvi" and is_admin(m.from_user.id))
def h_ep_settings(msg):
    uid = msg.from_user.id
    if not admin_media_perm(uid, "parts"):
        safe(bot.send_message, msg.chat.id, "❌ Qismlarni boshqarish ruxsati yo'q!")
        return
    sset(uid, "media_parts_code")
    safe(bot.send_message, msg.chat.id, "🎬 *Qismlar boshqaruvi*\n\nKontent kodi yoki nomini yozing:")


# ============================================================
#  ADMIN: ANIME O'CHIRISH
# ============================================================

@bot.message_handler(func=lambda m: m.text in ("🗑️ O'chirish", "🗑️ Delete Media") and is_admin(m.from_user.id))
def h_del(msg):
    uid = msg.from_user.id
    if not admin_media_perm(uid, "delete"):
        safe(bot.send_message, msg.chat.id, "❌ Sizda o'chirish ruxsati yo'q!"); return
    sset(uid, "media_del_code")
    safe(bot.send_message, msg.chat.id, "🗑️ *Kontentni o'chirish*\n\nKontent kodi yoki nomini yozing:")


@bot.message_handler(func=lambda m: m.text == "👥 Foydalanuvchilar" and is_admin(m.from_user.id))
def h_user_manage(msg):
    uid = msg.from_user.id
    if not admin_has_perm(uid, "user_manage"):
        safe(bot.send_message, msg.chat.id, "❌ Sizda foydalanuvchilarni boshqarish ruxsati yo'q.")
        return
    sset(uid, "user_manage_search")
    safe(bot.send_message, msg.chat.id,
         "👥 *Foydalanuvchini qidirish*\n\nTelegram ID yoki @username yuboring:")


def _user_manage_text(user):
    status = "Bloklangan" if user.get("blocked") else "Faol"
    return (
        "👥 *FOYDALANUVCHI PROFILI*\n\n"
        f"🆔 ID: `{user['user_id']}`\n"
        f"📛 Ism: {user.get('full_name') or '—'}\n"
        f"🔗 Username: @{user.get('username') or '—'}\n"
        f"🔧 Holati: *{status}*\n"
        f"💰 Tanga: {user.get('coins', 0)}\n"
        f"📅 Qo'shilgan: {str(user.get('join_date') or '—')[:19]}"
    )


def _user_manage_kb(user):
    target_id = int(user["user_id"])
    kb = types.InlineKeyboardMarkup(row_width=1)
    if target_id != OWNER_ID:
        if user.get("blocked"):
            kb.add(types.InlineKeyboardButton(
                "✅ Blokdan chiqarish", callback_data=f"UM_UNBLOCK|{target_id}"
            ))
        else:
            kb.add(types.InlineKeyboardButton(
                "🚫 Bloklash", callback_data=f"UM_BLOCK|{target_id}"
            ))
    kb.add(types.InlineKeyboardButton("🔙 Qidiruvga qaytish", callback_data="UM_BACK"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data.startswith(("UM_BLOCK|", "UM_UNBLOCK|", "UM_BACK")))
def cb_user_manage(call):
    uid = call.from_user.id
    if not admin_has_perm(uid, "user_manage"):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    if call.data == "UM_BACK":
        bot.answer_callback_query(call.id)
        sset(uid, "user_manage_search")
        safe(bot.send_message, call.message.chat.id, "👥 Telegram ID yoki @username yuboring:")
        return
    try:
        target_id = int(call.data.split("|", 1)[1])
    except (TypeError, ValueError):
        bot.answer_callback_query(call.id, "❌ Foydalanuvchi havolasi eskirgan.", show_alert=True)
        return
    if target_id == OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Ownerni bloklab bo'lmaydi.", show_alert=True)
        return
    user = get_user(target_id)
    if not user:
        bot.answer_callback_query(call.id, "❌ Foydalanuvchi topilmadi.", show_alert=True)
        return
    blocked = call.data.startswith("UM_BLOCK|")
    con = db(); c = con.cursor()
    c.execute("UPDATE users SET blocked=? WHERE user_id=?", (1 if blocked else 0, target_id))
    con.commit(); con.close()
    bot.answer_callback_query(call.id, "✅ Holat yangilandi.")
    updated = get_user(target_id) or user
    safe(bot.send_message, call.message.chat.id, _user_manage_text(updated),
         reply_markup=_user_manage_kb(updated))


@bot.message_handler(func=lambda m: m.text == "📜 Admin harakatlari")
def h_admin_actions(msg):
    if msg.from_user.id != OWNER_ID:
        safe(bot.send_message, msg.chat.id, "❌ Bu bo'lim faqat Owner uchun.")
        return
    rows = get_admin_actions(30)
    if not rows:
        safe(bot.send_message, msg.chat.id, "📜 Hozircha admin harakatlari yo'q.")
        return
    text = "📜 *ADMIN HARAKATLARI*\n\n"
    for row in rows:
        actor = row.get("full_name") or row.get("username") or row["admin_id"]
        target = row.get("anime_code") or "—"
        episode = ""
        if row.get("ep_num") is not None:
            episode = f" · {row.get('ep_type') or 'season'} {row['ep_num']}-qism"
        text += f"• `{row['created_at']}`\n  {actor} · {row['action']} · `{target}`{episode}\n\n"
    safe(bot.send_message, msg.chat.id, text)


@bot.callback_query_handler(func=lambda c: c.data in ("MEDDEL_YES", "MEDDEL_NO"))
def cb_media_delete_confirm(call):
    uid = call.from_user.id
    if not is_admin(uid) or not admin_media_perm(uid, "delete"):
        bot.answer_callback_query(call.id, "❌ O'chirish ruxsati yo'q.", show_alert=True)
        return
    si = sget(uid)
    code = (si.get("data") or {}).get("code")
    if call.data == "MEDDEL_NO":
        sclear(uid)
        bot.answer_callback_query(call.id, "Bekor qilindi")
        safe(
            bot.send_message, call.message.chat.id,
            "❌ Media o'chirish bekor qilindi.",
            reply_markup=admin_kb(uid),
        )
        return
    media = get_media_item(code) if code else None
    if not media:
        sclear(uid)
        bot.answer_callback_query(call.id, "❌ Media topilmadi.", show_alert=True)
        safe(bot.send_message, call.message.chat.id, "❌ Bu media endi mavjud emas.",
             reply_markup=admin_kb(uid))
        return
    ok = delete_media(media["code"])
    sclear(uid)
    bot.answer_callback_query(call.id, "✅ O'chirildi" if ok else "❌ O'chirilmadi")
    if ok:
        log_admin_action(uid, "media_deleted", media["code"])
        safe(
            bot.send_message, call.message.chat.id,
            f"✅ *{media['title']}* butunlay o'chirildi.\n"
            "Uning bo'limlari va bog'langan ma'lumotlari ham bazadan olib tashlandi.",
            reply_markup=admin_kb(uid),
        )
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Media o'chirishda xato yuz berdi.",
             reply_markup=admin_kb(uid))


# ============================================================
#  ADMIN: STATISTIKA
# ============================================================

@bot.message_handler(func=lambda m: m.text == "📊 Statistika" and is_admin(m.from_user.id))
def h_stats(msg):
    uid = msg.from_user.id
    if not admin_has_perm(uid, "stats"):
        safe(bot.send_message, msg.chat.id, "❌ Sizda bu funksiyaga ruxsat yo'q!"); return
    s = get_stats()
    media_lines = []
    for media_type in MEDIA_TYPES:
        media_lines.append(
            f"{media_type_icon(media_type)} {media_type_label(media_type)}: "
            f"*{s['media_counts'].get(media_type, 0)}*"
        )
    safe(bot.send_message, msg.chat.id,
        f"📊 *STATISTIKA*\n\n"
        f"👥 Jami foydalanuvchilar: *{s['total']}*\n"
        f"🆕 Bugun yangi: *{s['today']}*\n"
        f"✅ Faol bugun: *{s['active']}*\n"
        f"⭐ VIP: *{s['vip']}*\n"
        f"💎 Premium: *{s['premium']}*\n"
        f"🚫 Bloklagan: *{s['blocked']}*\n\n"
        f"🎞️ *UMUMIY KONTENT:* *{s['media_total']}*\n"
        + "\n".join(media_lines)
        + f"\n📁 Barcha bo'limlar: *{s['parts']}*\n\n"
        f"📅 *{local_now().strftime('%Y-%m-%d %H:%M')}*")


# ============================================================
#  ADMIN: SOZLAMALAR PANEL
# ============================================================

@bot.message_handler(func=lambda m: m.text in ("⚙️ Media sozlamalari", "⚙️ Sozlamalar") and is_admin(m.from_user.id))
def h_settings(msg):
    uid = msg.from_user.id
    if not is_admin(uid): return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📡 Kanal sozlamalari (Majburiy obuna)", callback_data="SET_CH"))
    if uid == OWNER_ID:
        kb.add(
            types.InlineKeyboardButton("👑 Admin boshqaruv", callback_data="SET_ADM"),
            types.InlineKeyboardButton("🔐 Admin ruxsatlari", callback_data="SET_PERMS"),
            types.InlineKeyboardButton("📡 Avtopost sozlamalari", callback_data="SET_AUTOPOST"),
            types.InlineKeyboardButton("💎 Status boshqaruv", callback_data="SET_ST"),
            types.InlineKeyboardButton("💾 Backup", callback_data="SET_BACKUP"),
        )
    elif admin_has_perm(uid, "autopost"):
        kb.add(types.InlineKeyboardButton("📡 Avtopost sozlamalari", callback_data="SET_AUTOPOST"))
    safe(bot.send_message, msg.chat.id, "⚙️ *SOZLAMALAR*\n\nNimani boshqarmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "SET_CH")
def cb_set_ch(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    chs = get_channels()
    txt = "📡 *KANAL SOZLAMALARI* (Majburiy obuna)\n\n"
    if chs:
        tg_chs = [c for c in chs if c.get('platform', 'telegram') == 'telegram']
        ig_chs = [c for c in chs if c.get('platform', 'telegram') == 'instagram']
        yt_chs = [c for c in chs if c.get('platform', 'telegram') == 'youtube']
        if tg_chs:
            txt += "📢 *Telegram*\n"
            for c in tg_chs:
                st_icon = '🟢' if c.get('active', 1) else '🔴'
                txt += f"  {st_icon} {c['channel_name']} (`{c['channel_id']}`)\n"
            txt += "\n"
        if ig_chs:
            txt += "📸 *Instagram*\n"
            for c in ig_chs:
                st_icon = '🟢' if c.get('active', 1) else '🔴'
                txt += f"  {st_icon} {c['channel_name']}\n"
            txt += "\n"
        if yt_chs:
            txt += "▶️ *YouTube*\n"
            for c in yt_chs:
                st_icon = '🟢' if c.get('active', 1) else '🔴'
                txt += f"  {st_icon} {c['channel_name']}\n"
    else:
        txt += "Hozircha kanal yo'q."
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ Kanal qo'shish", callback_data="CH_ADD"))
    kb.add(
        types.InlineKeyboardButton("🟢/🔴 Yoqish/O'chirish", callback_data="CH_TOGGLE"),
        types.InlineKeyboardButton("🗑️ O'chirish", callback_data="CH_DEL"),
    )
    kb.add(types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"))
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "SET_ADM")
def cb_set_adm(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    admins = list_admins()
    txt = "👑 *ADMIN BOSHQARUV*\n\n"
    txt += "\n".join(f"• `{a['user_id']}` — {str(a['added_date'])[:10]}" for a in admins) if admins else "Hozircha admin yo'q."
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Admin qo'shish", callback_data="ADM_ADD"),
        types.InlineKeyboardButton("➖ O'chirish", callback_data="ADM_DEL"),
    )
    kb.add(types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"))
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "SET_ST")
def cb_set_st(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("💎 Premium berish", callback_data="ST_GIVE_PREM"),
        types.InlineKeyboardButton("⭐ VIP berish", callback_data="ST_GIVE_VIP"),
        types.InlineKeyboardButton("🗑️ Status o'chirish", callback_data="ST_REMOVE"),
        types.InlineKeyboardButton("📋 VIP/Premium ro'yxati", callback_data="ST_LIST"),
        types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"),
    )
    safe(bot.send_message, call.message.chat.id, "💎 *STATUS BOSHQARUV*\n\nNima qilmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "BACK_SET")
def cb_back_set(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.from_user.id): return
    uid = call.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📡 Kanal sozlamalari (Majburiy obuna)", callback_data="SET_CH"))
    if uid == OWNER_ID:
        kb.add(
            types.InlineKeyboardButton("👑 Admin boshqaruv", callback_data="SET_ADM"),
            types.InlineKeyboardButton("🔐 Admin ruxsatlari", callback_data="SET_PERMS"),
            types.InlineKeyboardButton("📡 Avtopost sozlamalari", callback_data="SET_AUTOPOST"),
            types.InlineKeyboardButton("💎 Status boshqaruv", callback_data="SET_ST"),
            types.InlineKeyboardButton("💾 Backup", callback_data="SET_BACKUP"),
        )
    try:
        bot.edit_message_text("⚙️ *SOZLAMALAR*\n\nNimani boshqarmoqchisiz?",
                              call.message.chat.id, call.message.message_id, reply_markup=kb)
    except Exception:
        safe(bot.send_message, call.message.chat.id, "⚙️ *SOZLAMALAR*\n\nNimani boshqarmoqchisiz?", reply_markup=kb)


# ============================================================
#  ADMIN RUXSATLARINI BOSHQARISH (faqat Owner)
# ============================================================

def _perms_kb(admin_uid):
    """Admin ruxsatlari tugmalar paneli."""
    perms = get_admin_perms(admin_uid)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, label in PERM_LIST:
        icon = "✅" if perms.get(key) else "❌"
        kb.add(types.InlineKeyboardButton(
            f"{label}: {icon}", callback_data=f"TPERM_{admin_uid}_{key}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Adminlar ro'yxatiga", callback_data="SET_PERMS"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "SET_PERMS")
def cb_set_perms(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    admins = list_admins()
    if not admins:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"))
        safe(bot.send_message, call.message.chat.id,
            "🔐 *ADMIN RUXSATLARI*\n\nHozircha admin yo'q.", reply_markup=kb)
        return
    txt = "🔐 *ADMIN RUXSATLARI*\n\nRuxsatlarini boshqarish uchun adminni tanlang:"
    kb = types.InlineKeyboardMarkup(row_width=1)
    for a in admins:
        u = get_user(a["user_id"])
        name = ""
        if u:
            name = u.get("full_name") or u.get("username") or ""
        label = f"👤 {name} ({a['user_id']})" if name else f"👤 {a['user_id']}"
        kb.add(types.InlineKeyboardButton(label, callback_data=f"SHOWPERM_{a['user_id']}"))
    kb.add(types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"))
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("SHOWPERM_"))
def cb_showperm(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    admin_uid = int(call.data[9:])
    u = get_user(admin_uid)
    name = ""
    if u:
        name = u.get("username") or u.get("full_name") or ""
        uname_str = f"@{name}" if u.get("username") else name
    else:
        uname_str = str(admin_uid)
    txt = f"🔐 *Admin ruxsatlari*\n\n👤 Admin: {uname_str}\n\nRuxsatni bosib yoqing/o'chiring:"
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=_perms_kb(admin_uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("TPERM_"))
def cb_tperm(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Faqat Owner uchun.", show_alert=True)
        return
    parts = call.data.split("_", 2)
    if len(parts) != 3:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri ruxsat.", show_alert=True)
        return
    try:
        admin_uid = int(parts[1])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri admin ID.", show_alert=True)
        return
    perm = parts[2]
    if not toggle_admin_perm(admin_uid, perm):
        bot.answer_callback_query(call.id, "❌ Noto'g'ri ruxsat.", show_alert=True)
        return
    # Tugmalarni yangilash
    perms = get_admin_perms(admin_uid)
    perm_label = next((lb for k, lb in PERM_LIST if k == perm), perm)
    new_icon = "✅" if perms.get(perm) else "❌"
    bot.answer_callback_query(call.id, f"{perm_label}: {new_icon}", show_alert=False)
    try:
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id,
            reply_markup=_perms_kb(admin_uid)
        )
    except Exception:
        pass


# ============================================================
#  AVTOPOST SOZLAMALARI (faqat Owner)
# ============================================================

def _autopost_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("➕ Avtopost kanalini qo'shish", callback_data="APS_ADD"),
        types.InlineKeyboardButton("📋 Avtopost kanallari", callback_data="APS_LIST"),
        types.InlineKeyboardButton("📝 Tomosha qilish tugmasi matni", callback_data="APS_BTN"),
        types.InlineKeyboardButton("📡 Kanal qatori", callback_data="APS_MAIN_TAG"),
        types.InlineKeyboardButton("📋 Avtopost tarixi", callback_data="APS_HISTORY"),
        types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"),
    )
    return kb


def _autopost_menu_kb_for(uid):
    if uid == OWNER_ID:
        return _autopost_menu_kb()
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📋 Avtopost tarixi", callback_data="APS_HISTORY"),
        types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "SET_AUTOPOST")
def cb_set_autopost(call):
    bot.answer_callback_query(call.id)
    if not _can_use_autopost(call.from_user.id): return
    btn_text = get_autopost_setting("watch_btn_text", "✨ TOMOSHA QILISH ✨")
    chs = get_autopost_channels()
    active = sum(1 for c in chs if c["active"])
    txt = (
        f"📡 *AVTOPOST SOZLAMALARI*\n\n"
        f"📺 Jami kanallar: *{len(chs)}* ta\n"
        f"🟢 Faol kanallar: *{active}* ta\n"
        f"🔘 Tugma matni: *{btn_text}*\n\n"
        f"📡 Kanal qatori: *📡 {get_main_channel_tag()}*\n\n"
        f"⚠️ Bu bo'lim majburiy obuna kanallaridan *butunlay alohida!*"
    )
    safe(bot.send_message, call.message.chat.id, txt,
         reply_markup=_autopost_menu_kb_for(call.from_user.id))


@bot.callback_query_handler(func=lambda c: c.data == "APS_HISTORY")
def cb_aps_history(call):
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    rows = get_autopost_history(20, uid=None if uid == OWNER_ID else uid)
    if not rows:
        safe(bot.send_message, call.message.chat.id,
            "📋 *AVTOPOST TARIXI*\n\nHozircha muvaffaqiyatli yoki xatolik bilan qayd etilgan postlar yo'q.",
            reply_markup=_autopost_menu_kb_for(uid))
        return
    safe(bot.send_message, call.message.chat.id,
        "📋 *AVTOPOST TARIXI*\n\nKerakli yozuvni tanlang:",
        reply_markup=_history_menu_keyboard_for(uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("APH_DETAIL_"))
def cb_aph_detail(call):
    uid = call.from_user.id
    try:
        history_id = int(call.data[11:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi noto'g'ri.", show_alert=True)
        return
    row = get_history_item(history_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi topilmadi.", show_alert=True)
        return
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak.", show_alert=True)
        return
    if uid != OWNER_ID and row["posted_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Bu tarix yozuvi sizga tegishli emas.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    status = "✅ Muvaffaqiyatli joylandi" if row["status"] == "success" else "❌ Yuborilmadi"
    ep = ""
    if row.get("ep_num"):
        ep = f"\n📺 {row.get('season') or '1'}-fasl | {row['ep_num']}-qism"
    text = (
        "📋 *AVTOPOST TARIXI*\n\n"
        f"⛩️ {row.get('anime_title') or row.get('anime_code')}\n"
        f"📌 Turi: {_history_post_type_label(row.get('post_type'))}{ep}\n"
        f"📡 Kanal: {row.get('channel_name') or row.get('channel_id')}\n"
        f"👤 Joyladi: {row.get('posted_by_name') or row.get('posted_by')}\n"
        f"🕒 {row.get('posted_at')}\n"
        f"{status}"
    )
    if row.get("error"):
        text += f"\n\nℹ️ {row['error']}"
    safe(bot.send_message, call.message.chat.id, text,
         reply_markup=_history_keyboard(row["id"]))


@bot.callback_query_handler(func=lambda c: c.data.startswith("APH_VIEW_"))
def cb_aph_view(call):
    uid = call.from_user.id
    try:
        history_id = int(call.data[9:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi noto'g'ri.", show_alert=True)
        return
    row = get_history_item(history_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi topilmadi.", show_alert=True)
        return
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak.", show_alert=True)
        return
    if uid != OWNER_ID and row["posted_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    _draft_preview(call.message.chat.id, _draft_from_history(row), "👀 *Avval joylangan post:*")
    safe(bot.send_message, call.message.chat.id,
         "📋 Post ma'lumotlari:", reply_markup=_history_keyboard(row["id"]))


@bot.callback_query_handler(func=lambda c: c.data.startswith("APH_DELETE_"))
def cb_aph_delete(call):
    uid = call.from_user.id
    try:
        history_id = int(call.data[11:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi noto'g'ri.", show_alert=True)
        return
    row = get_history_item(history_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi topilmadi.", show_alert=True)
        return
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak.", show_alert=True)
        return
    if uid != OWNER_ID and row["posted_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    delete_history_item(row["id"])
    safe(bot.send_message, call.message.chat.id,
         "✅ Tarix yozuvi o'chirildi.", reply_markup=_history_menu_keyboard_for(uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("APH_REPOST_"))
def cb_aph_repost(call):
    uid = call.from_user.id
    try:
        history_id = int(call.data[11:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi noto'g'ri.", show_alert=True)
        return
    row = get_history_item(history_id)
    if not row:
        bot.answer_callback_query(call.id, "❌ Tarix yozuvi topilmadi.", show_alert=True)
        return
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak.", show_alert=True)
        return
    if uid != OWNER_ID and row["posted_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q.", show_alert=True)
        return
    active_channels = get_autopost_channels(only_active=True)
    if not active_channels:
        bot.answer_callback_query(call.id, "❌ Faol avtopost kanallari yo'q.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    draft = _draft_from_history(row)
    sset(uid, "ap_repost_wait", draft)
    safe(bot.send_message, call.message.chat.id,
         "🔁 *Qayta joylashga tayyor.*\n\n"
         "Post qayta bazaga qo'shilmaydi va anime kodi o'zgarmaydi.\n"
         "Qayerga yuborishni tanlang:", reply_markup=_autopost_offer_kb(
             len(get_autopost_channels(only_active=True))))


@bot.callback_query_handler(func=lambda c: c.data == "APS_LIST")
def cb_aps_list(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    chs = get_autopost_channels()
    if not chs:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("➕ Kanal qo'shish", callback_data="APS_ADD"))
        kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="SET_AUTOPOST"))
        safe(bot.send_message, call.message.chat.id,
            "📋 *AVTOPOST KANALLARI*\n\nHozircha kanal yo'q.", reply_markup=kb)
        return
    txt = "📋 *AVTOPOST KANALLARI*\n\n"
    for ch in chs:
        st_icon = "🟢" if ch["active"] else "🔴"
        txt += f"{st_icon} *{ch['channel_name']}* (`{ch['channel_id']}`)\n"
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in chs:
        st_icon = "🟢" if ch["active"] else "🔴"
        kb.add(types.InlineKeyboardButton(
            f"{st_icon} {ch['channel_name']}", callback_data=f"APCH_{ch['channel_id']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="SET_AUTOPOST"))
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("APCH_"))
def cb_apch(call):
    """Avtopost kanalini boshqarish."""
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cid = call.data[5:]
    con = db(); cur = con.cursor()
    cur.execute("SELECT * FROM autopost_channels WHERE channel_id=?", (cid,))
    row = cur.fetchone(); con.close()
    if not row:
        safe(bot.send_message, call.message.chat.id, "❌ Kanal topilmadi!"); return
    ch = dict(row)
    st = "🟢 Yoqilgan" if ch["active"] else "🔴 O'chirilgan"
    txt = (
        f"📡 *Kanal boshqaruvi*\n\n"
        f"📋 Nom: *{ch['channel_name']}*\n"
        f"🆔 ID: `{ch['channel_id']}`\n"
        f"Holat: {st}"
    )
    toggle_lbl = "🔴 O'chirish" if ch["active"] else "🟢 Yoqish"
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(toggle_lbl, callback_data=f"APTGL_{cid}"),
        types.InlineKeyboardButton("🗑️ Kanaldan olib tashlash", callback_data=f"APDRM_{cid}"),
        types.InlineKeyboardButton("🔙 Orqaga", callback_data="APS_LIST"),
    )
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("APTGL_"))
def cb_aptgl(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cid = call.data[6:]
    new_state = toggle_autopost_channel(cid)
    state_txt = "🟢 Yoqildi" if new_state else "🔴 O'chirildi"
    safe(bot.send_message, call.message.chat.id,
        f"✅ Kanal holati o'zgardi: *{state_txt}*",
        reply_markup=_autopost_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data.startswith("APDRM_"))
def cb_apdrm(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cid = call.data[6:]
    if del_autopost_channel(cid):
        safe(bot.send_message, call.message.chat.id,
            "✅ Kanal avtopost ro'yxatidan o'chirildi.\n\n"
            "⚠️ Majburiy obuna kanallariga hech qanday ta'sir qilinmadi.",
            reply_markup=_autopost_menu_kb())
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Kanal topilmadi!")


@bot.callback_query_handler(func=lambda c: c.data == "APS_ADD")
def cb_aps_add(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "aps_ch_id")
    safe(bot.send_message, call.message.chat.id,
        "📡 *Avtopost kanalini qo'shish*\n\n"
        "Kanal username yoki ID sini yuboring:\n"
        "_(Masalan: @anibestrasmiy yoki -100xxxxxxxxx)_\n\n"
        "⚠️ Botni kanalga admin qilib, xabar yuborish ruxsatini bering!")


@bot.callback_query_handler(func=lambda c: c.data == "APS_BTN")
def cb_aps_btn(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cur_text = get_autopost_setting("watch_btn_text", "✨ TOMOSHA QILISH ✨")
    sset(call.from_user.id, "aps_btn_text")
    safe(bot.send_message, call.message.chat.id,
        f"📝 *Tomosha qilish tugmasi matni*\n\n"
        f"Hozirgi matn: *{cur_text}*\n\n"
        f"Yangi matnni yozing:\n"
        f"_(Masalan: 🍿 TOMOSHA QILISH yoki ▶️ HOZIROQ KO'RING)_")


@bot.callback_query_handler(func=lambda c: c.data == "APS_MAIN_TAG")
def cb_aps_main_tag(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID:
        return
    current_tag = get_main_channel_tag()
    sset(call.from_user.id, "aps_main_tag")
    safe(
        bot.send_message,
        call.message.chat.id,
        f"📡 *Postdagi kanal qatori*\n\n"
        f"Hozirgi qiymat: *📡 {current_tag}*\n\n"
        "Yangi kanal username sini yuboring:\n"
        "_Masalan: @anibestrasmiy_\n\n"
        "Standart qiymatga qaytarish uchun `-` yuboring.",
    )


# ============================================================
#  BACKUP CALLBACKS (faqat Owner)
# ============================================================

def _backup_menu_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📤 Backup yaratish", callback_data="BKP_CREATE"),
        types.InlineKeyboardButton("📥 Backupni tiklash", callback_data="BKP_RESTORE"),
        types.InlineKeyboardButton("📋 Backup ma'lumotlari", callback_data="BKP_INFO"),
        types.InlineKeyboardButton("🔙 Sozlamalarga", callback_data="BACK_SET"),
    )
    return kb


@bot.callback_query_handler(func=lambda c: c.data == "SET_BACKUP")
def cb_set_backup(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "❌ Faqat Owner uchun!", show_alert=True); return
    safe(bot.send_message, call.message.chat.id,
        "💾 *BACKUP TIZIMI*\n\nNimani qilmoqchisiz?", reply_markup=_backup_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data == "BKP_CREATE")
def cb_bkp_create(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    safe(bot.send_message, call.message.chat.id, "⏳ *Backup yaratilmoqda...*")
    fname, fsize_kb, err = create_backup()
    if err or not fname:
        logger.error("Backup yaratilmadi: %s", err)
        safe(bot.send_message, call.message.chat.id,
            "❌ Backup yaratishda xato yuz berdi. Qaytadan urinib ko'ring.",
            reply_markup=_backup_menu_kb())
        return
    try:
        with open(fname, "rb") as f:
            bot.send_document(
                call.from_user.id, f,
                caption=(
                    f"✅ *Backup muvaffaqiyatli yaratildi!*\n\n"
                    f"📁 Fayl: `{fname}`\n"
                    f"💾 Hajmi: {fsize_kb} KB\n"
                    f"📅 Sana: {LAST_BACKUP_INFO.get('date','—')}"
                ),
            )
    except Exception as e:
        logger.error(f"Backup fayl yuborish: {e}")
        safe(bot.send_message, call.message.chat.id,
            "⚠️ Backup yaratildi, lekin faylni yuborishda xato yuz berdi.")
    safe(bot.send_message, call.message.chat.id,
        "✅ *Backup muvaffaqiyatli yaratildi!*\nFayl Telegram orqali yuborildi.",
        reply_markup=_backup_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data == "BKP_INFO")
def cb_bkp_info(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    if not LAST_BACKUP_INFO:
        safe(bot.send_message, call.message.chat.id,
            "📋 *Backup ma'lumotlari*\n\n❌ Hali backup yaratilmagan.",
            reply_markup=_backup_menu_kb())
        return
    txt = (
        f"📦 *Backup ma'lumotlari*\n\n"
        f"📅 Sana: `{LAST_BACKUP_INFO.get('date','—')}`\n"
        f"📁 Fayl nomi: `{LAST_BACKUP_INFO.get('filename','—')}`\n"
        f"💾 Fayl hajmi: `{LAST_BACKUP_INFO.get('size','—')}`"
    )
    safe(bot.send_message, call.message.chat.id, txt, reply_markup=_backup_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data == "BKP_RESTORE")
def cb_bkp_restore(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "bkp_file_wait")
    safe(bot.send_message, call.message.chat.id,
        "📥 *Backupni tiklash*\n\nBackup JSON faylini yuboring:\n_(bekor qilish: /cancel)_")


@bot.callback_query_handler(func=lambda c: c.data == "BKP_RESTORE_YES")
def cb_bkp_restore_yes(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    si = sget(call.from_user.id)
    backup_data = si.get("data", {}).get("backup_data")
    if not backup_data:
        safe(bot.send_message, call.message.chat.id, "❌ Ma'lumot topilmadi. Qaytadan urinib ko'ring."); return
    sclear(call.from_user.id)
    safe(bot.send_message, call.message.chat.id, "⏳ *Backup tiklanmoqda...*")
    ok, err = restore_backup_from_data(backup_data)
    if ok:
        safe(bot.send_message, call.message.chat.id,
            "✅ *Backup muvaffaqiyatli tiklandi!*", reply_markup=_backup_menu_kb())
    else:
        safe(bot.send_message, call.message.chat.id,
            "❌ Backupni tiklashda xato yuz berdi. Eski ma'lumotlar saqlab qolindi.",
            reply_markup=_backup_menu_kb())


@bot.callback_query_handler(func=lambda c: c.data == "BKP_RESTORE_NO")
def cb_bkp_restore_no(call):
    bot.answer_callback_query(call.id)
    sclear(call.from_user.id)
    safe(bot.send_message, call.message.chat.id,
        "❌ *Tiklash bekor qilindi.*", reply_markup=_backup_menu_kb())


# ============================================================
#  ADMIN: BROADCAST
# ============================================================

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast" and is_admin(m.from_user.id))
def h_bc_start(msg):
    uid = msg.from_user.id
    if not admin_has_perm(uid, "broadcast"):
        safe(bot.send_message, msg.chat.id, "❌ Sizda bu funksiyaga ruxsat yo'q!"); return
    sset(uid, "bc_msg")
    safe(bot.send_message, msg.chat.id,
        "📢 *Broadcast*\n\nYubormoqchi bo'lgan xabaringizni yuboring:\n_(bekor qilish: /cancel)_")


# ============================================================
#  ADMIN: ADMIN BOSHQARUV
# ============================================================

@bot.message_handler(func=lambda m: m.text == "👑 Admin boshqaruv" and is_admin(m.from_user.id))
def h_admin_mgmt(msg):
    if msg.from_user.id != OWNER_ID:
        safe(bot.send_message, msg.chat.id, "❌ Bu funksiya faqat Owner uchun!"); return
    admins = list_admins()
    txt = "👑 *ADMIN BOSHQARUV*\n\n"
    if admins:
        for a in admins:
            txt += f"• `{a['user_id']}` — {str(a['added_date'])[:10]}\n"
    else:
        txt += "Hozircha admin yo'q.\n"
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Admin qo'shish", callback_data="ADM_ADD"),
        types.InlineKeyboardButton("➖ O'chirish", callback_data="ADM_DEL"),
    )
    safe(bot.send_message, msg.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "ADM_ADD")
def cb_adm_add(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "adm_add")
    safe(bot.send_message, call.message.chat.id, "➕ Yangi admin ID sini yozing:")


@bot.callback_query_handler(func=lambda c: c.data == "ADM_DEL")
def cb_adm_del(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    admins = list_admins()
    if not admins:
        safe(bot.send_message, call.message.chat.id, "❌ Adminlar yo'q."); return
    kb = types.InlineKeyboardMarkup()
    for a in admins:
        kb.add(types.InlineKeyboardButton(f"🗑️ {a['user_id']}", callback_data=f"DELA_{a['user_id']}"))
    safe(bot.send_message, call.message.chat.id, "O'chirmoqchi bo'lgan adminni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("DELA_"))
def cb_dela(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    uid = int(call.data[5:])
    if remove_admin(uid):
        try:
            bot.edit_message_text(f"✅ Admin `{uid}` o'chirildi.", call.message.chat.id, call.message.message_id)
        except Exception:
            safe(bot.send_message, call.message.chat.id, f"✅ Admin `{uid}` o'chirildi.")
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Xato yuz berdi!")


# ============================================================
#  KANAL BOSHQARUV (Majburiy obuna)
# ============================================================

@bot.message_handler(func=lambda m: m.text == "📡 Kanal boshqaruv" and is_admin(m.from_user.id))
def h_ch_mgmt(msg):
    chs = get_channels()
    txt = "📡 *KANAL BOSHQARUV* (Majburiy obuna)\n\n"
    txt += "\n".join(f"• {c['channel_name']} ({c['channel_id']})" for c in chs) if chs else "Hozircha kanal yo'q."
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Qo'shish", callback_data="CH_ADD"),
        types.InlineKeyboardButton("➖ O'chirish", callback_data="CH_DEL"),
    )
    safe(bot.send_message, msg.chat.id, txt, reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "CH_ADD")
def cb_ch_add(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 Telegram", callback_data="CH_PLAT_TG"))
    kb.add(types.InlineKeyboardButton("📸 Instagram", callback_data="CH_PLAT_IG"))
    kb.add(types.InlineKeyboardButton("▶️ YouTube", callback_data="CH_PLAT_YT"))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="SET_CH"))
    safe(bot.send_message, call.message.chat.id,
        "📌 Qaysi platformani qo'shmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "CH_PLAT_TG")
def cb_ch_plat_tg(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "ch_tg_waiting")
    safe(bot.send_message, call.message.chat.id,
        "📝 Telegram kanal username'i yoki havolasini yuboring.\n\nMasalan:\n`@anibest`")


@bot.callback_query_handler(func=lambda c: c.data == "CH_PLAT_IG")
def cb_ch_plat_ig(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "ch_ig_waiting")
    safe(bot.send_message, call.message.chat.id,
        "📝 Instagram profil username'i yoki havolasini yuboring.\n\nMasalan:\n`@anibest`\nyoki:\n`https://instagram.com/anibest`")


@bot.callback_query_handler(func=lambda c: c.data == "CH_PLAT_YT")
def cb_ch_plat_yt(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "ch_yt_waiting")
    safe(bot.send_message, call.message.chat.id,
        "📝 YouTube kanal havolasini yuboring.\n\nMasalan:\n`https://youtube.com/@anibest`")


@bot.callback_query_handler(func=lambda c: c.data == "CH_TOGGLE")
def cb_ch_toggle_list(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    chs = get_channels()
    if not chs:
        safe(bot.send_message, call.message.chat.id, "❌ Kanal yo'q."); return
    kb = types.InlineKeyboardMarkup()
    for ch in chs:
        icon = PLATFORM_ICONS.get(ch.get('platform', 'telegram'), '📢')
        st_icon = '🟢' if ch.get('active', 1) else '🔴'
        kb.add(types.InlineKeyboardButton(
            f"{st_icon} {icon} {ch['channel_name']}",
            callback_data=f"TGLC_{ch['channel_id']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="SET_CH"))
    safe(bot.send_message, call.message.chat.id,
        "🟢/🔴 Yoqish yoki o'chirish uchun kanalni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("TGLC_"))
def cb_tglc(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cid = call.data[5:]
    toggle_channel(cid)
    # Yangilangan ro'yxatni ko'rsat
    chs = get_channels()
    if not chs:
        safe(bot.send_message, call.message.chat.id, "❌ Kanal yo'q."); return
    kb = types.InlineKeyboardMarkup()
    for ch in chs:
        icon = PLATFORM_ICONS.get(ch.get('platform', 'telegram'), '📢')
        st_icon = '🟢' if ch.get('active', 1) else '🔴'
        kb.add(types.InlineKeyboardButton(
            f"{st_icon} {icon} {ch['channel_name']}",
            callback_data=f"TGLC_{ch['channel_id']}"
        ))
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="SET_CH"))
    try:
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=kb)
    except Exception:
        safe(bot.send_message, call.message.chat.id,
            "🟢/🔴 Yoqish yoki o'chirish uchun kanalni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "CH_DEL")
def cb_ch_del(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    chs = get_channels()
    if not chs:
        safe(bot.send_message, call.message.chat.id, "❌ Kanal yo'q."); return
    kb = types.InlineKeyboardMarkup()
    for ch in chs:
        icon = PLATFORM_ICONS.get(ch.get('platform', 'telegram'), '📢')
        kb.add(types.InlineKeyboardButton(f"🗑️ {icon} {ch['channel_name']}", callback_data=f"DELC_{ch['channel_id']}"))
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="SET_CH"))
    safe(bot.send_message, call.message.chat.id, "🗑️ O'chirmoqchi bo'lgan kanalni tanlang:", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("DELC_"))
def cb_delc(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    cid = call.data[5:]
    if del_channel(cid):
        try:
            bot.edit_message_text("✅ Kanal o'chirildi.", call.message.chat.id, call.message.message_id)
        except Exception:
            safe(bot.send_message, call.message.chat.id, "✅ Kanal o'chirildi.")
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Xato yuz berdi!")


# ============================================================
#  STATUS BOSHQARUV
# ============================================================

def _find_user_by_input(t):
    if t.lstrip("-").isdigit():
        return int(t)
    if t.startswith("@"):
        con = db(); c = con.cursor()
        c.execute("SELECT user_id FROM users WHERE username=?", (t[1:],))
        row = c.fetchone(); con.close()
        return row["user_id"] if row else None
    return None


def remove_status(uid):
    con = db(); c = con.cursor()
    c.execute(
        "UPDATE users SET status='user', vip_expires=NULL, premium_expires=NULL WHERE user_id=?",
        (uid,)
    )
    con.commit(); con.close()


@bot.message_handler(func=lambda m: m.text == "💎 Status boshqaruv" and is_admin(m.from_user.id))
def h_status_mgmt(msg):
    if msg.from_user.id != OWNER_ID:
        safe(bot.send_message, msg.chat.id, "❌ Bu funksiya faqat Owner uchun!"); return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("💎 Premium berish", callback_data="ST_GIVE_PREM"),
        types.InlineKeyboardButton("⭐ VIP berish", callback_data="ST_GIVE_VIP"),
        types.InlineKeyboardButton("🗑️ Status o'chirish", callback_data="ST_REMOVE"),
        types.InlineKeyboardButton("📋 VIP/Premium ro'yxati", callback_data="ST_LIST"),
    )
    safe(bot.send_message, msg.chat.id, "💎 *STATUS BOSHQARUV*\n\nNima qilmoqchisiz?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data == "ST_GIVE_PREM")
def cb_st_give_prem(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "give_prem")
    safe(bot.send_message, call.message.chat.id,
        "💎 *Premium berish*\n\nFoydalanuvchi ID yoki @username yozing:")


@bot.callback_query_handler(func=lambda c: c.data == "ST_GIVE_VIP")
def cb_st_give_vip(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "give_vip")
    safe(bot.send_message, call.message.chat.id,
        "⭐ *VIP berish*\n\nFoydalanuvchi ID yoki @username yozing:")


@bot.callback_query_handler(func=lambda c: c.data == "ST_REMOVE")
def cb_st_remove(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    sset(call.from_user.id, "remove_status")
    safe(bot.send_message, call.message.chat.id,
        "🗑️ *Status o'chirish*\n\nFoydalanuvchi ID yoki @username yozing:")


@bot.callback_query_handler(func=lambda c: c.data == "ST_LIST")
def cb_st_list(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id != OWNER_ID: return
    con = db(); c = con.cursor()
    c.execute(
        "SELECT user_id, username, full_name, status, vip_expires, premium_expires "
        "FROM users WHERE status IN ('vip','premium') ORDER BY status DESC"
    )
    rows = [dict(r) for r in c.fetchall()]; con.close()
    if not rows:
        safe(bot.send_message, call.message.chat.id, "❌ Hozircha VIP/Premium foydalanuvchi yo'q."); return
    txt = "📋 *VIP / PREMIUM RO'YXATI*\n\n"
    for r in rows:
        ico = "💎" if r["status"] == "premium" else "⭐"
        exp = r.get("premium_expires") or r.get("vip_expires") or ""
        txt += f"{ico} `{r['user_id']}` — {r['full_name'] or r['username'] or 'Nomalum'} | {str(exp)[:10]}\n"
    safe(bot.send_message, call.message.chat.id, txt)


# ============================================================
#  EPISODE CALLBACKS (ko'rish uchun)
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data.startswith(("EPG_", "EPG|")))
def cb_epg(call):
    bot.answer_callback_query(call.id)
    if not require_sub_cb(call): return
    if call.data.startswith("EPG|"):
        _, code, etype, page = call.data.split("|", 3)
    else:
        _, code, etype, page = call.data.split("_", 3)
    show_eps(call.message.chat.id, call.from_user.id, code, etype, int(page),
             edit_mid=call.message.message_id)


@bot.callback_query_handler(func=lambda c: c.data.startswith(("SEP_", "SEP|")))
def cb_sep(call):
    bot.answer_callback_query(call.id)
    if not require_sub_cb(call): return
    if call.data.startswith("SEP|"):
        _, code, num, etype, page = call.data.split("|", 4)
    else:
        _, code, num, etype, page = call.data.split("_", 4)
    ep = get_ep(code, int(num), etype)
    a  = get_anime(code)
    if not ep or not a:
        media = get_media_item(code)
        if media:
            part_type = "ova" if etype == "ova" else "episode"
            parts = get_media_parts(media["id"], part_type)
            part = next((p for p in parts if int(p["part_number"]) == int(num)), None)
            if part:
                record_media_watch(
                    call.from_user.id, media["id"], int(num), part_type, 1,
                )
                _send_media_part(
                    call.message.chat.id, part, call.from_user.id,
                )
                return
        safe(bot.send_message, call.message.chat.id, "❌ Qism topilmadi."); return
    record_watch(call.from_user.id, code, int(num), etype)
    _send_episode_file(call.message.chat.id, a, ep, int(num), etype, int(page))


@bot.callback_query_handler(func=lambda c: c.data.startswith("ABCK_"))
def cb_abck(call):
    if not require_sub_cb(call): return
    bot.answer_callback_query(call.id)
    code = call.data[5:]
    show_anime(call.message.chat.id, call.from_user.id, code, edit_mid=call.message.message_id)


# ============================================================
#  JANR MULTI-SELECT
# ============================================================

# ============================================================
#  AVTOPOST CALLBACK HANDLERS
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data == "AP_PREVIEW")
def cb_ap_preview(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        return
    draft = _draft_from_state(uid)
    if draft:
        _draft_preview(call.message.chat.id, draft)


@bot.callback_query_handler(func=lambda c: c.data == "AP_EDIT")
def cb_ap_edit_start(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        return
    si = sget(uid)
    draft = _draft_from_state(uid)
    if not draft:
        safe(bot.send_message, call.message.chat.id, "❌ Post sessiyasi tugagan.")
        return
    draft["edit_return_state"] = si.get("state", "ap_anime_wait")
    _draft_store(uid, draft)
    safe(bot.send_message, call.message.chat.id,
         "✏️ *POSTNI TAHRIRLASH*\n\nFaqat tayyorlanayotgan post nusxasi o'zgaradi. Anime bazasidagi asl ma'lumotlar saqlanadi.",
         reply_markup=_draft_keyboard(uid))


@bot.callback_query_handler(func=lambda c: c.data in (
    "APE_TEXT", "APE_GENRES", "APE_PHOTO", "APE_VIDEO",
    "APE_MEDIA_CLEAR", "APE_BUTTON", "APE_PREVIEW", "APE_DONE",
    "APE_GENRES_SKIP", "APE_GENRES_CLEAR", "APE_BACK"
))
def cb_ap_edit(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        return
    draft = _draft_from_state(uid)
    if not draft:
        safe(bot.send_message, call.message.chat.id, "❌ Post sessiyasi tugagan.")
        return
    action = call.data
    if action == "APE_TEXT":
        draft["edit_return_state"] = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, "ap_edit_text", draft)
        safe(bot.send_message, call.message.chat.id, "📝 Avtopost matnini yuboring:")
    elif action == "APE_GENRES":
        draft["edit_return_state"] = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, "ap_edit_genres", draft)
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(
            types.InlineKeyboardButton("⏭️ Skip", callback_data="APE_GENRES_SKIP"),
            types.InlineKeyboardButton("🗑️ Tasnifni olib tashlash", callback_data="APE_GENRES_CLEAR"),
            types.InlineKeyboardButton("⬅️ Orqaga", callback_data="APE_BACK"),
        )
        safe(bot.send_message, call.message.chat.id,
             "📝 Tasnifni yozing yoki “Skip” tugmasini bosing:", reply_markup=kb)
    elif action == "APE_PHOTO":
        draft["edit_return_state"] = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, "ap_edit_photo", draft)
        safe(bot.send_message, call.message.chat.id, "🖼️ Yangi rasmni yuboring:")
    elif action == "APE_VIDEO":
        draft["edit_return_state"] = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, "ap_edit_video", draft)
        safe(bot.send_message, call.message.chat.id, "🎬 Yangi qisqa videoni yuboring:")
    elif action == "APE_MEDIA_CLEAR":
        draft["media_id"] = None
        draft["media_type"] = None
        _draft_store(uid, draft)
        safe(bot.send_message, call.message.chat.id, "✅ Media faqat shu post nusxasidan olib tashlandi.",
             reply_markup=_draft_keyboard(uid))
    elif action == "APE_BUTTON":
        draft["edit_return_state"] = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, "ap_edit_button", draft)
        safe(bot.send_message, call.message.chat.id, "🔘 Tugma matnini yuboring:")
    elif action == "APE_PREVIEW":
        _draft_preview(call.message.chat.id, draft)
        safe(bot.send_message, call.message.chat.id, "✏️ Tahrirlashni davom ettiring:",
             reply_markup=_draft_keyboard(uid))
    elif action == "APE_DONE":
        return_state = draft.get("edit_return_state") or "ap_anime_wait"
        draft.pop("edit_return_state", None)
        _draft_store(uid, draft)
        sset(uid, return_state, draft)
        safe(bot.send_message, call.message.chat.id, "✅ Post tayyor.",
             reply_markup=_autopost_offer_kb(len(get_autopost_channels(only_active=True))))
    elif action in ("APE_GENRES_SKIP", "APE_BACK"):
        return_state = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, return_state, draft)
        safe(bot.send_message, call.message.chat.id, "↩️ Hozirgi tasnif saqlandi.",
             reply_markup=_draft_keyboard(uid))
    elif action == "APE_GENRES_CLEAR":
        draft["genres"] = None
        draft["text"] = _replace_post_genres(draft.get("text", ""), None)
        return_state = draft.get("edit_return_state") or "ap_anime_wait"
        sset(uid, return_state, draft)
        safe(bot.send_message, call.message.chat.id, "✅ Tasnif shu postdan olib tashlandi.",
             reply_markup=_draft_keyboard(uid))


@bot.callback_query_handler(func=lambda c: c.data == "AP_ALL")
def cb_ap_all(call):
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    si = sget(uid)
    st = si.get("state", "")
    if st in ("ap_anime_wait", "ap_ep_wait", "ap_existing_wait", "ap_repost_wait") or st.startswith("ap_edit_"):
        draft = _draft_from_state(uid)
        if not draft:
            safe(bot.send_message, call.message.chat.id, "❌ Post sessiyasi tugagan!"); return
        ok, fail = _send_draft(uid, draft)
        _finish_autopost_action(uid, draft)
        safe(bot.send_message, call.message.chat.id,
            f"📡 *Yuborildi!*\n\n✅ Muvaffaqiyatli: *{ok}* kanal\n❌ Xato: *{fail}* kanal",
            reply_markup=admin_kb(uid) if draft.get("post_type") != "new_episode" else None)
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Faol avtopost sessiyasi topilmadi.")


@bot.callback_query_handler(func=lambda c: c.data == "AP_SELECT")
def cb_ap_select(call):
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    if sget(uid).get("state") not in (
        "ap_anime_wait", "ap_ep_wait", "ap_existing_wait", "ap_repost_wait"
    ):
        safe(bot.send_message, call.message.chat.id, "❌ Faol avtopost sessiyasi topilmadi.")
        return
    active_chs = get_autopost_channels(only_active=True)
    if not active_chs:
        safe(bot.send_message, call.message.chat.id, "❌ Faol avtopost kanallar yo'q!"); return
    safe(bot.send_message, call.message.chat.id,
        "📡 Qaysi kanalga yubormoqchisiz?",
        reply_markup=_autopost_channel_select_kb(active_chs))


@bot.callback_query_handler(func=lambda c: c.data.startswith("APC_"))
def cb_apc(call):
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    cid = call.data[4:]
    si = sget(uid)
    st = si.get("state", "")
    if st in (
        "ap_anime_wait", "ap_ep_wait", "ap_existing_wait", "ap_repost_wait"
    ) or st.startswith("ap_edit_"):
        draft = _draft_from_state(uid)
        if not draft:
            safe(bot.send_message, call.message.chat.id, "❌ Post sessiyasi tugagan!"); return
        ok, fail = _send_draft(uid, draft, [cid])
        _finish_autopost_action(uid, draft)
    else:
        safe(bot.send_message, call.message.chat.id, "❌ Faol avtopost sessiyasi topilmadi.")
        return

    safe(bot.send_message, call.message.chat.id,
        f"📡 *Yuborildi!*\n\n✅ Muvaffaqiyatli: *{ok}* kanal\n❌ Xato: *{fail}* kanal",
        reply_markup=admin_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data == "AP_CANCEL")
def cb_ap_cancel(call):
    uid = call.from_user.id
    if not _can_use_autopost(uid):
        bot.answer_callback_query(call.id, "❌ Avtopost ruxsati kerak!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    draft = _draft_from_state(uid)
    _finish_autopost_action(uid, draft)
    try:
        bot.edit_message_text("❌ *E'lon bekor qilindi.*",
                              call.message.chat.id, call.message.message_id)
    except Exception:
        safe(bot.send_message, call.message.chat.id, "❌ *E'lon bekor qilindi.*")
    safe(bot.send_message, call.message.chat.id, "⚙️ Admin panelga qaytildi.", reply_markup=admin_kb(uid))


# ============================================================
#  EP TYPE SELECT
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data in ("EPT_season", "EPT_ova"))
def cb_ept(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id; si = sget(uid); d = si.get("data", {})
    et = "season" if call.data == "EPT_season" else "ova"
    d["ep_type"] = et; sset(uid, "ep_file", d)
    nn = next_ep_num(d["anime_code"], et)
    tname = "Asosiy" if et == "season" else "OVA"
    bot.edit_message_text(
            f"🎬 *{d['anime_title']}*\n📹 Tur: *{tname}*\n🔢 Keyingi qism: *{nn}*\n\n"
        f"Fayl yuboring:\n_(Bir nechta faylni bir vaqtda tanlasangiz hammasi qabul qilinadi)_",
        call.message.chat.id, call.message.message_id)


# ============================================================
#  BROADCAST CALLBACKS
# ============================================================

@bot.callback_query_handler(func=lambda c: c.data in ("BC_SEND","BC_EDIT","BC_CANCEL"))
def cb_bc(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if not is_admin(uid): return
    si = sget(uid); d = si.get("data", {})
    if call.data == "BC_CANCEL":
        sclear(uid)
        bot.edit_message_text("❌ Broadcast bekor qilindi.", call.message.chat.id, call.message.message_id); return
    if call.data == "BC_EDIT":
        sset(uid, "bc_msg", {})
        bot.edit_message_text("✏️ Yangi xabarni yuboring:", call.message.chat.id, call.message.message_id); return
    if call.data == "BC_SEND":
        sclear(uid)
        users = all_user_ids()
        from_chat = d.get("from_chat")
        msg_id    = d.get("msg_id")
        notify_chat = call.message.chat.id
        bot.edit_message_text(f"📢 {len(users)} ta foydalanuvchiga yuborilmoqda...",
                              notify_chat, call.message.message_id)

        def _do_broadcast():
            ok = fail = 0
            for i, tuid in enumerate(users):
                try:
                    bot.copy_message(tuid, from_chat, msg_id); ok += 1
                except Exception as e:
                    if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                        con = db(); c = con.cursor()
                        c.execute("UPDATE users SET blocked=1 WHERE user_id=?", (tuid,))
                        con.commit(); con.close()
                    fail += 1
                if i % 25 == 0: time.sleep(1)
            safe(bot.send_message, notify_chat,
                f"📊 *Broadcast tugadi!*\n\n✅ Muvaffaqiyatli: *{ok}*\n❌ Muvaffaqiyatsiz: *{fail}*",
                reply_markup=admin_kb(uid))

        threading.Thread(target=_do_broadcast, daemon=True).start()


# ============================================================
#  QO'LDA POST TIZIMI
# ============================================================

# --- DB helpers ---

def mp_add(text, category, image_id, video_id, audio_id, age_limit, created_by, draft=None):
    con = db(); c = con.cursor()
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    draft = draft or {}
    c.execute(
        """INSERT INTO manual_posts
        (text,custom_text,post_type,category,image_id,video_id,audio_id,age_limit,anime_title,
         description,genres,season,episodes,voice,min_status,anime_code,
         created_by,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            text, draft.get("custom_text"), draft.get("post_type") or "new_anime", category,
            image_id, video_id, audio_id, age_limit,
            draft.get("anime_title"), draft.get("description"), draft.get("genres"),
            _mp_normalize_season(draft.get("season")), draft.get("episodes"),
            draft.get("voice"), draft.get("min_status"), draft.get("anime_code"),
            created_by, now,
        ),
    )
    post_id = c.lastrowid
    con.commit(); con.close()
    return post_id


def mp_get(post_id):
    con = db(); c = con.cursor()
    c.execute("SELECT * FROM manual_posts WHERE id=?", (post_id,))
    row = c.fetchone(); con.close()
    return dict(row) if row else None


def mp_list(uid=None, limit=20):
    con = db(); c = con.cursor()
    if uid is None or uid == OWNER_ID:
        c.execute("SELECT * FROM manual_posts ORDER BY id DESC LIMIT ?", (limit,))
    else:
        c.execute(
            "SELECT * FROM manual_posts WHERE created_by=? ORDER BY id DESC LIMIT ?",
            (uid, limit),
        )
    rows = [dict(r) for r in c.fetchall()]; con.close()
    return rows


def mp_delete(post_id):
    con = db(); c = con.cursor()
    c.execute(
        "UPDATE manual_posts SET status='deleted' WHERE id=? AND status!='deleted'",
        (post_id,),
    )
    ok = c.rowcount > 0
    con.commit(); con.close()
    return ok


def mp_update(post_id, field, value):
    allowed = {
        "text", "custom_text", "post_type", "category", "image_id", "video_id", "audio_id", "age_limit",
        "anime_title", "description", "genres", "season", "episodes", "voice",
        "min_status", "anime_code",
    }
    if field not in allowed: return False
    if field == "anime_code" and (not value or not get_anime(value)):
        return False
    con = db(); c = con.cursor()
    if field == "image_id":
        c.execute(
            "UPDATE manual_posts SET image_id=?,video_id=NULL,audio_id=NULL "
            "WHERE id=? AND status!='deleted'",
            (value, post_id),
        )
    elif field == "video_id":
        c.execute(
            "UPDATE manual_posts SET video_id=?,image_id=NULL,audio_id=NULL "
            "WHERE id=? AND status!='deleted'",
            (value, post_id),
        )
    elif field == "audio_id":
        c.execute(
            "UPDATE manual_posts SET audio_id=?,image_id=NULL,video_id=NULL "
            "WHERE id=? AND status!='deleted'",
            (value, post_id),
        )
    elif field == "text":
        c.execute(
            "UPDATE manual_posts SET text=?,custom_text=? "
            "WHERE id=? AND status!='deleted'",
            (value or "", value, post_id),
        )
    elif field in {
        "post_type", "category", "age_limit", "anime_title", "description",
        "genres", "season", "episodes", "voice", "min_status", "anime_code",
    }:
        c.execute(
            f"UPDATE manual_posts SET {field}=?,custom_text=NULL "
            "WHERE id=? AND status!='deleted'",
            (value, post_id),
        )
    else:
        c.execute(
            f"UPDATE manual_posts SET {field}=? WHERE id=? AND status!='deleted'",
            (value, post_id),
        )
    con.commit(); con.close()
    return c.rowcount > 0


def _can_manual_post(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "manual_post"))


def _can_mp_history(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "manual_post_history"))


def _can_mp_edit(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "manual_post_edit"))


def _can_mp_delete(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "manual_post_delete"))


def _can_mp_repost(uid):
    return uid == OWNER_ID or (is_admin(uid) and admin_has_perm(uid, "manual_post_repost"))


# --- Build & send helpers ---

def _mp_clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _mp_normalize_season(value):
    """3 -> 3-fasl, 3-fasl -> 3-fasl; empty means omitted."""
    value = _mp_clean(value)
    if not value:
        return ""
    if re.search(r"-?\s*fasl$", value, flags=re.IGNORECASE):
        number = re.sub(r"-?\s*fasl$", "", value, flags=re.IGNORECASE).strip()
        return f"{number}-fasl" if number else value
    return f"{value}-fasl"


def _mp_build_text(draft):
    """Talab qilingan manual anime post matnini bo'sh qatorsiz yaratadi."""
    title = _post_field(draft.get("anime_title") or draft.get("text"))
    parts = [f"⛩️ {title}"] if title else []
    season = _format_season(draft.get("season"))
    episodes = _format_episode(draft.get("episodes"))
    is_episode = draft.get("post_type") == "new_episode"
    season_icon = "📺" if is_episode else "📽️"
    if season and episodes:
        parts.append(f"{season_icon} {season} | 🎞️ {episodes}")
    elif season:
        parts.append(f"{season_icon} {season}")
    elif episodes:
        parts.append(f"🎞️ {episodes}")
    voice = _post_field(draft.get("voice"))
    if is_episode:
        parts.append("✨ Yangi qism joylandi!")
        if voice:
            parts.append(f"🎙️ {voice}")
    else:
        if voice:
            parts.append(f"🎙️ {voice}")
        parts.append("✨ Anime joylandi!")
    return ensure_channel_tag("\n".join(parts))


def _mp_draft_text(draft):
    draft = dict(draft or {})
    # Yangi oqim bitta media bilan cheklanadi; eski postlar uchun ham
    # yetkazib berishdan oldin aralash media holatini xavfsiz tozalaymiz.
    if draft.get("image_id"):
        draft["video_id"] = None
        draft["audio_id"] = None
    elif draft.get("video_id"):
        draft["audio_id"] = None
    draft["text"] = ensure_channel_tag(
        draft.get("custom_text") or _mp_build_text(draft)
    )
    return draft


def _mp_media_prompt(chat_id):
    safe(
        bot.send_message,
        chat_id,
        "9️⃣ *Media tanlang:*\n\n"
        "Bitta postga faqat rasm yoki qisqa video qo'shiladi.\n"
        "Media qo'shmasdan davom etish ham mumkin.",
        reply_markup=_mp_media_kb(),
    )


def _mp_media_type(draft):
    if draft.get("video_id"):
        return "video"
    if draft.get("image_id"):
        return "photo"
    if draft.get("audio_id"):
        return "voice"
    return "text"


def _mp_send_one(channel_id, draft):
    """Yuborilgan xabarni va media turini qaytaradi."""
    draft = _mp_draft_text(draft)
    if not draft.get("anime_code") or not get_anime(draft["anime_code"]):
        raise ValueError("Anime kodi bazada topilmadi")
    text = draft["text"]
    kb = get_watch_inline_kb(draft.get("anime_code"))
    if draft.get("video_id"):
        message = bot.send_video(
            channel_id, draft["video_id"], caption=text, reply_markup=kb, parse_mode=None
        )
        return message, "video"
    if draft.get("image_id"):
        message = bot.send_photo(
            channel_id, draft["image_id"], caption=text, reply_markup=kb, parse_mode=None
        )
        return message, "photo"
    if draft.get("audio_id"):
        message = bot.send_voice(
            channel_id, draft["audio_id"], caption=text, reply_markup=kb, parse_mode=None
        )
        return message, "voice"
    message = bot.send_message(channel_id, text, reply_markup=kb, parse_mode=None)
    return message, "text"


def _mp_delivery_add(post_id, channel, message_id, media_type, status="success", error=None):
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    con = db(); c = con.cursor()
    c.execute(
        """INSERT INTO manual_post_deliveries
        (post_id,channel_id,channel_name,message_id,media_type,status,error,posted_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            post_id, channel.get("channel_id"), channel.get("channel_name"),
            message_id, media_type, status, error, now, now,
        ),
    )
    con.commit(); con.close()


def _mp_delivery_update(delivery_id, message_id=None, media_type=None, status=None, error=None):
    updates = []
    values = []
    if message_id is not None:
        updates.append("message_id=?"); values.append(message_id)
    if media_type is not None:
        updates.append("media_type=?"); values.append(media_type)
    if status is not None:
        updates.append("status=?"); values.append(status)
    updates.append("error=?"); values.append(error)
    updates.append("updated_at=?")
    values.append(local_now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(delivery_id)
    con = db(); c = con.cursor()
    c.execute(f"UPDATE manual_post_deliveries SET {', '.join(updates)} WHERE id=?", values)
    con.commit(); con.close()


def _mp_deliveries(post_id):
    con = db(); c = con.cursor()
    c.execute(
        "SELECT * FROM manual_post_deliveries WHERE post_id=? ORDER BY id ASC",
        (post_id,),
    )
    rows = [dict(row) for row in c.fetchall()]
    con.close()
    return rows


def _mp_delivery_summary(post_id):
    deliveries = _mp_deliveries(post_id)
    success = [
        str(row.get("channel_name") or row.get("channel_id"))
        for row in deliveries
        if row.get("status") == "success"
    ]
    failed = [
        str(row.get("channel_name") or row.get("channel_id"))
        for row in deliveries
        if row.get("status") == "failed"
    ]
    lines = []
    if success:
        lines.append("✅ Yetkazildi: " + ", ".join(success[:20]))
    if failed:
        lines.append("❌ Xato: " + ", ".join(failed[:20]))
    return "\n".join(lines) or "📡 Hech bir kanalga yuborilmadi."


def _mp_post_snapshot(post_id, draft):
    """Tarix va keyingi tahrir uchun manual postning to'liq nusxasini saqlaydi."""
    draft = _mp_draft_text(draft)
    message_map = {}
    for delivery in _mp_deliveries(post_id):
        if delivery.get("message_id") is not None:
            message_map.setdefault(str(delivery["channel_id"]), []).append(
                delivery["message_id"]
            )
    now = local_now().strftime("%Y-%m-%d %H:%M:%S")
    con = db(); c = con.cursor()
    c.execute(
        """UPDATE manual_posts SET text=?,custom_text=?,post_type=?,anime_title=?,description=?,genres=?,
        season=?,episodes=?,voice=?,min_status=?,anime_code=?,age_limit=?,
        category=?,image_id=?,video_id=?,audio_id=?,channel_messages=?,
        last_posted_at=? WHERE id=?""",
        (
            draft.get("text", ""), draft.get("custom_text"),
            draft.get("post_type") or "new_anime",
            draft.get("anime_title"), draft.get("description"),
            draft.get("genres"), _mp_normalize_season(draft.get("season")),
            draft.get("episodes"), draft.get("voice"), draft.get("min_status"),
            draft.get("anime_code"), draft.get("age_limit"), draft.get("category"),
            draft.get("image_id"), draft.get("video_id"), draft.get("audio_id"),
            json.dumps(message_map, ensure_ascii=False), now, post_id,
        ),
    )
    con.commit(); con.close()


def _mp_sync_post(post_id, force_replace=False):
    """Tahrirlangan manual postni avval joylangan xabarlar bilan sinxronlaydi."""
    post = mp_get(post_id)
    if not post:
        return []
    draft = _mp_draft_text(post)
    result = []
    for delivery in _mp_deliveries(post_id):
        if delivery.get("status") != "success" or not delivery.get("message_id"):
            continue
        channel_id = delivery["channel_id"]
        old_message_id = delivery["message_id"]
        old_media_type = delivery.get("media_type") or "text"
        new_media_type = _mp_media_type(draft)
        try:
            if force_replace or old_media_type != new_media_type:
                new_message, actual_media_type = _mp_send_one(channel_id, draft)
                try:
                    bot.delete_message(channel_id, old_message_id)
                except Exception as delete_error:
                    logger.warning(
                        f"Eski manual postni o'chirish xatosi [{channel_id}]: {delete_error}"
                    )
                _mp_delivery_update(
                    delivery["id"], new_message.message_id, actual_media_type, "success", None
                )
            elif new_media_type in {"photo", "video", "voice"}:
                bot.edit_message_caption(
                    channel_id,
                    old_message_id,
                    caption=draft["text"],
                    reply_markup=get_watch_inline_kb(draft.get("anime_code")),
                    parse_mode=None,
                )
            else:
                bot.edit_message_text(
                    draft["text"],
                    channel_id,
                    old_message_id,
                    reply_markup=get_watch_inline_kb(draft.get("anime_code")),
                    parse_mode=None,
                )
            result.append((delivery.get("channel_name") or channel_id, True, None))
        except Exception as exc:
            logger.error(f"Manual postni yangilash xatosi [{channel_id}]: {exc}")
            _mp_delivery_update(delivery["id"], status="failed", error=str(exc))
            result.append((delivery.get("channel_name") or channel_id, False, str(exc)))
    _mp_post_snapshot(post_id, draft)
    return result


def _mp_delete_from_channels(post_id):
    """Postga biriktirilgan barcha Telegram xabarlarini o'chirishga urinadi."""
    result = []
    for delivery in _mp_deliveries(post_id):
        if delivery.get("status") not in ("success", "failed"):
            continue
        message_id = delivery.get("message_id")
        channel_id = delivery.get("channel_id")
        if not message_id:
            result.append((delivery.get("channel_name") or channel_id, False, "Message ID topilmadi"))
            continue
        try:
            bot.delete_message(channel_id, message_id)
            _mp_delivery_update(delivery["id"], status="deleted", error=None)
            result.append((delivery.get("channel_name") or channel_id, True, None))
        except Exception as exc:
            logger.error(f"Manual postni o'chirish xatosi [{channel_id}]: {exc}")
            _mp_delivery_update(delivery["id"], status="delete_failed", error=str(exc))
            result.append((delivery.get("channel_name") or channel_id, False, str(exc)))
    return result


def _mp_send_to_channels(draft, uid):
    """Qo'lda postni barcha faol avtopost kanallariga yuboradi."""
    channels = get_autopost_channels(only_active=True)
    if not channels:
        return 0, 0
    if not draft.get("anime_code") or not get_anime(draft["anime_code"]):
        logger.error("Qo'lda post bekor qilindi: anime kodi bazada topilmadi [%s]", draft.get("anime_code"))
        return 0, len(channels)
    post_id = draft.get("post_id")
    ok = 0; fail = 0
    for ch in channels:
        try:
            message, media_type = _mp_send_one(ch["channel_id"], draft)
            if post_id:
                _mp_delivery_add(post_id, ch, message.message_id, media_type)
            ok += 1
        except Exception as e:
            logger.error(f"Qo'lda post kanal [{ch['channel_id']}]: {e}")
            if post_id:
                _mp_delivery_add(post_id, ch, None, _mp_media_type(draft), "failed", str(e))
            fail += 1
    if post_id:
        _mp_post_snapshot(post_id, draft)
    return ok, fail


def _mp_preview_send(chat_id, draft, prefix="👀 *Preview (kanalga yuborilmaydi):*"):
    draft = _mp_draft_text(draft)
    text = draft["text"]
    kb = get_watch_inline_kb(draft.get("anime_code"))
    safe(bot.send_message, chat_id, prefix)
    if draft.get("video_id"):
        safe(
            bot.send_video, chat_id, draft["video_id"], caption=text,
            reply_markup=kb, parse_mode=None
        )
    elif draft.get("image_id"):
        safe(
            bot.send_photo, chat_id, draft["image_id"], caption=text,
            reply_markup=kb, parse_mode=None
        )
    elif draft.get("audio_id"):
        safe(
            bot.send_voice, chat_id, draft["audio_id"], caption=text,
            reply_markup=kb, parse_mode=None
        )
    else:
        safe(bot.send_message, chat_id, text, reply_markup=kb, parse_mode=None)


def _mp_confirm_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("👀 Preview", callback_data="MP_PREVIEW"),
        types.InlineKeyboardButton("📡 Barcha faol kanallarga joylash", callback_data="MP_SEND"),
        types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="MP_EDIT_DRAFT"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MP_CANCEL"),
    )
    return kb


def _mp_skip_kb(callback_data):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("⏭️ Skip", callback_data=callback_data))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MP_CANCEL"))
    return kb


def _mp_history_kb(uid):
    posts = mp_list(uid)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for p in posts:
        short = (p.get("text") or "Post")[:35]
        kind = "📺" if p.get("post_type") == "new_episode" else "🆕"
        kb.add(types.InlineKeyboardButton(
            f"{kind} {short} · {str(p['created_at'])[:10]}",
            callback_data=f"MPD_{p['id']}",
        ))
    kb.add(types.InlineKeyboardButton("🔙 Admin panelga", callback_data="MP_BACK_ADMIN"))
    return kb


def _mp_type_edit_kb(post_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            "🆕 Yangi anime", callback_data=f"MPTYPE_new_anime_{post_id}"
        ),
        types.InlineKeyboardButton(
            "📺 Yangi qism", callback_data=f"MPTYPE_new_episode_{post_id}"
        ),
        types.InlineKeyboardButton("❌ Bekor", callback_data=f"MPD_{post_id}"),
    )
    return kb


def _mp_detail_kb(post_id, uid):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("👀 Ko'rish", callback_data=f"MPV_{post_id}"))
    post = mp_get(post_id)
    is_deleted = post and post.get("status") == "deleted"
    if _can_mp_edit(uid) and not is_deleted:
        kb.add(types.InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"MPE_{post_id}"))
    if _can_mp_repost(uid) and not is_deleted:
        kb.add(types.InlineKeyboardButton("🔁 Qayta joylash", callback_data=f"MPR_{post_id}"))
    if _can_mp_delete(uid) and not is_deleted:
        kb.add(types.InlineKeyboardButton("🗑️ O'chirish", callback_data=f"MPDD_{post_id}"))
    kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data="MP_HISTORY"))
    return kb


# --- Message handlers ---

@bot.message_handler(func=lambda m: m.text == "✍️ Qo'lda post" and is_admin(m.from_user.id))
def h_manual_post_start(msg):
    uid = msg.from_user.id
    if not _can_manual_post(uid):
        safe(bot.send_message, msg.chat.id, "❌ Sizda qo'lda post yaratish ruxsati yo'q!"); return
    channels = get_autopost_channels(only_active=True)
    if not channels:
        safe(bot.send_message, msg.chat.id,
             "❌ Faol avtopost kanallari yo'q.\n\n"
             "Avval ⚙️ Sozlamalar → Avtopost sozlamalari dan kanal qo'shing."); return
    sset(uid, "mp_type_wait", {})
    safe(bot.send_message, msg.chat.id,
         "✍️ *Qo'lda post yaratish*\n\n"
         "Avval post turini tanlang:",
         reply_markup=_mp_type_kb())


def _mp_type_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("🆕 Yangi anime", callback_data="MP_TYPE_NEW_ANIME"),
        types.InlineKeyboardButton("📺 Yangi qism", callback_data="MP_TYPE_NEW_EPISODE"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MP_CANCEL"),
    )
    return kb


def _mp_media_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("⏭️ Mediasiz davom etish", callback_data="MP_SKIP_MEDIA"),
        types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MP_CANCEL"),
    )
    return kb


def _mp_code_prompt(chat_id):
    safe(
        bot.send_message,
        chat_id,
        "🔟 *Anime kodi* ni yozing:\n\n"
        "Kod bot bazasida tekshiriladi.",
    )


@bot.callback_query_handler(func=lambda c: c.data in (
    "MP_TYPE_NEW_ANIME", "MP_TYPE_NEW_EPISODE"
))
def cb_mp_type_choice(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    post_type = (
        "new_episode"
        if call.data == "MP_TYPE_NEW_EPISODE"
        else "new_anime"
    )
    sset(uid, "mp_title_wait", {"post_type": post_type})
    safe(
        bot.send_message,
        call.message.chat.id,
        "1️⃣ *Anime nomi* — majburiy:\n\n"
        "⛩️ Anime nomini yozing:\n"
        "Masalan: Mushoku Tensei: Omadsizning qayta tug'ilishi\n\n"
        "Bekor qilish uchun /cancel bosing.",
    )


def _mp_next_prompt(chat_id, uid, state, draft, prompt, skip_callback=None):
    sset(uid, state, draft)
    safe(
        bot.send_message,
        chat_id,
        prompt,
        reply_markup=_mp_skip_kb(skip_callback) if skip_callback else None,
    )


def _mp_status_kb():
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("🆓", callback_data="MP_STATUS_FREE"),
        types.InlineKeyboardButton("💎 Premium", callback_data="MP_STATUS_PREMIUM"),
        types.InlineKeyboardButton("⭐ VIP", callback_data="MP_STATUS_VIP"),
    )
    kb.add(types.InlineKeyboardButton("⏭️ Skip", callback_data="MP_SKIP_STATUS"))
    kb.add(types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MP_CANCEL"))
    return kb


@bot.callback_query_handler(func=lambda c: c.data in (
    "MP_STATUS_FREE", "MP_STATUS_PREMIUM", "MP_STATUS_VIP", "MP_SKIP_STATUS"
))
def cb_mp_status_choice(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    si = sget(uid)
    draft = dict(si.get("data", {}))
    choices = {
        "MP_STATUS_FREE": "🆓",
        "MP_STATUS_PREMIUM": "💎 Premium",
        "MP_STATUS_VIP": "⭐ VIP",
        "MP_SKIP_STATUS": None,
    }
    draft["min_status"] = choices[call.data]
    _mp_next_prompt(
        call.message.chat.id,
        uid,
        "mp_age_wait",
        draft,
        "8️⃣ *Yosh cheklovi* ni yozing (masalan: 13+):",
        "MP_SKIP_AGE",
    )


@bot.message_handler(func=lambda m: m.text == "📋 Qo'lda postlar" and is_admin(m.from_user.id))
def h_manual_post_list(msg):
    uid = msg.from_user.id
    if not _can_mp_history(uid):
        safe(bot.send_message, msg.chat.id, "❌ Sizda postlar tarixini ko'rish ruxsati yo'q!"); return
    posts = mp_list(uid)
    if not posts:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Admin panelga", callback_data="MP_BACK_ADMIN"))
        safe(bot.send_message, msg.chat.id,
             "📋 *QO'LDA POSTLAR TARIXI*\n\nHozircha post yo'q.", reply_markup=kb); return
    safe(bot.send_message, msg.chat.id,
         "📋 *QO'LDA POSTLAR TARIXI*\n\nKerakli postni tanlang:",
         reply_markup=_mp_history_kb(uid))


# --- Skip callbacks (post yaratish jarayonida) ---

@bot.callback_query_handler(func=lambda c: c.data in (
    "MP_SKIP_DESCRIPTION", "MP_SKIP_GENRES", "MP_SKIP_SEASON",
    "MP_SKIP_EPISODES", "MP_SKIP_VOICE", "MP_SKIP_STATUS", "MP_SKIP_AGE"
))
def cb_mp_skip(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    si = sget(uid); d = si.get("data", {})
    action = call.data
    next_steps = {
        "MP_SKIP_DESCRIPTION": ("mp_genres_wait", "3️⃣ *Janr yoki tasnif* ni yozing:", "MP_SKIP_GENRES"),
        "MP_SKIP_GENRES": ("mp_season_wait", "4️⃣ *Fasl* sonini yozing (masalan: 3):", "MP_SKIP_SEASON"),
        "MP_SKIP_SEASON": ("mp_episodes_wait", "5️⃣ *Qismlar* sonini yoki qo'shimcha qismlarni yozing:", "MP_SKIP_EPISODES"),
        "MP_SKIP_EPISODES": ("mp_voice_wait", "6️⃣ *Ovoz* turini yozing (masalan: O'zbekcha):", "MP_SKIP_VOICE"),
        "MP_SKIP_VOICE": ("mp_status_wait", "7️⃣ *Holat* ni yozing (masalan: 🆓 yoki Premium):", "MP_SKIP_STATUS"),
        "MP_SKIP_STATUS": ("mp_age_wait", "8️⃣ *Yosh cheklovi* ni yozing (masalan: 13+):", "MP_SKIP_AGE"),
    }
    if action == "MP_SKIP_AGE":
        d["age_limit"] = None
        sset(uid, "mp_media_wait", d)
        _mp_media_prompt(call.message.chat.id)
        return
    next_state, prompt, next_skip = next_steps[action]
    field_for_action = {
        "MP_SKIP_DESCRIPTION": "description",
        "MP_SKIP_GENRES": "genres",
        "MP_SKIP_SEASON": "season",
        "MP_SKIP_EPISODES": "episodes",
        "MP_SKIP_VOICE": "voice",
        "MP_SKIP_STATUS": "min_status",
    }[action]
    d[field_for_action] = None
    sset(uid, next_state, d)
    safe(bot.send_message, call.message.chat.id, prompt, reply_markup=_mp_skip_kb(next_skip))


@bot.callback_query_handler(func=lambda c: c.data == "MP_SKIP_MEDIA")
def cb_mp_skip_media(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    draft = dict(sget(uid).get("data", {}))
    draft["image_id"] = None
    draft["video_id"] = None
    draft["audio_id"] = None
    sset(uid, "mp_code_wait", draft)
    _mp_code_prompt(call.message.chat.id)


# --- Preview/Send/Cancel callbacks ---

@bot.callback_query_handler(func=lambda c: c.data == "MP_PREVIEW")
def cb_mp_preview(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    si = sget(uid); d = si.get("data", {})
    _mp_preview_send(call.message.chat.id, d)
    safe(bot.send_message, call.message.chat.id,
         "📋 Tasdiqlaysizmi?", reply_markup=_mp_confirm_kb())


@bot.callback_query_handler(func=lambda c: c.data == "MP_SEND")
def cb_mp_send(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    si = sget(uid); d = si.get("data", {})
    d = _mp_draft_text(d)
    if not d.get("anime_title") or not d.get("anime_code"):
        safe(bot.send_message, call.message.chat.id, "❌ Post ma'lumotlari to'liq emas!")
        return
    if not get_anime(d["anime_code"]):
        safe(bot.send_message, call.message.chat.id, "❌ Anime kodi bazada topilmadi. Post joylanmadi!")
        return
    if not get_autopost_channels(only_active=True):
        safe(bot.send_message, call.message.chat.id,
             "❌ Faol avtopost kanali topilmadi. Post joylanmadi!")
        return
    post_id = mp_add(
        text=d.get("text", ""),
        category=d.get("category"),
        image_id=d.get("image_id"),
        video_id=d.get("video_id"),
        audio_id=d.get("audio_id"),
        age_limit=d.get("age_limit"),
        created_by=uid,
        draft=d,
    )
    d["post_id"] = post_id
    ok, fail = _mp_send_to_channels(d, uid)
    sclear(uid)
    safe(bot.send_message, call.message.chat.id,
         f"✅ *Post joylandi!*\n\n"
         f"💾 Saqlandi (ID: #{post_id})\n"
         f"📡 Muvaffaqiyatli: *{ok}* kanal\n"
         f"❌ Xato: *{fail}* kanal\n\n"
         f"{_mp_delivery_summary(post_id)}",
         reply_markup=admin_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data == "MP_EDIT_DRAFT")
def cb_mp_edit_draft(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    fields = (
        ("anime_title", "⛩️ Anime nomi"),
        ("description", "📝 Tasnif"),
        ("genres", "🎭 Janr"),
        ("season", "📽️ Fasl"),
        ("episodes", "🎞️ Qismlar"),
        ("voice", "🎙️ Ovoz"),
        ("min_status", "🎯 Holat"),
        ("age_limit", "⚠️ Yosh cheklovi"),
        ("anime_code", "🔑 Anime kodi"),
    )
    for field, label in fields:
        kb.add(types.InlineKeyboardButton(label, callback_data=f"MPDEF_{field}"))
    kb.add(types.InlineKeyboardButton("⬅️ Tasdiqlashga qaytish", callback_data="MP_BACK_CONFIRM"))
    safe(bot.send_message, call.message.chat.id, "✏️ Qaysi maydonni tahrirlaysiz?",
         reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPDEF_"))
def cb_mp_edit_draft_field(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    field = call.data[6:]
    allowed = {
        "anime_title", "description", "genres", "season", "episodes",
        "voice", "min_status", "age_limit", "anime_code",
    }
    if field not in allowed:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri maydon!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    draft = dict(sget(uid).get("data", {}))
    sset(uid, "mp_draft_edit", {"field": field, "draft": draft})
    prompts = {
        "anime_title": "⛩️ Yangi anime nomini yozing:",
        "description": "📝 Yangi tasnifni yozing (o'chirish uchun `-`):",
        "genres": "🎭 Yangi janrni yozing (o'chirish uchun `-`):",
        "season": "📽️ Yangi faslni yozing (o'chirish uchun `-`):",
        "episodes": "🎞️ Yangi qismlar sonini yozing (o'chirish uchun `-`):",
        "voice": "🎙️ Yangi ovozni yozing (o'chirish uchun `-`):",
        "min_status": "🎯 Yangi holatni yozing (o'chirish uchun `-`):",
        "age_limit": "⚠️ Yangi yosh cheklovini yozing (o'chirish uchun `-`):",
        "anime_code": "🔑 Yangi anime kodini yozing:",
    }
    safe(bot.send_message, call.message.chat.id, prompts[field])


@bot.callback_query_handler(func=lambda c: c.data == "MP_BACK_CONFIRM")
def cb_mp_back_confirm(call):
    uid = call.from_user.id
    if not _can_manual_post(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    state_data = sget(uid).get("data", {})
    # Maydon tanlash bosqichida state data {field, draft} ko'rinishida bo'ladi.
    # To'g'ridan-to'g'ri tasdiqlash oynasidan kelganda esa data draftning o'zi.
    draft = state_data.get("draft", state_data) if isinstance(state_data, dict) else {}
    sset(uid, "mp_confirm_wait", draft)
    _mp_preview_send(call.message.chat.id, draft)
    safe(bot.send_message, call.message.chat.id, "📋 Tasdiqlaysizmi?",
         reply_markup=_mp_confirm_kb())


@bot.callback_query_handler(func=lambda c: c.data == "MP_CANCEL")
def cb_mp_cancel_new(call):
    uid = call.from_user.id
    bot.answer_callback_query(call.id)
    sclear(uid)
    safe(bot.send_message, call.message.chat.id,
         "❌ Post yaratish bekor qilindi.", reply_markup=admin_kb(uid))


# --- History/Detail callbacks ---

@bot.callback_query_handler(func=lambda c: c.data == "MP_HISTORY")
def cb_mp_history(call):
    uid = call.from_user.id
    if not _can_mp_history(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    posts = mp_list(uid)
    if not posts:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 Admin panelga", callback_data="MP_BACK_ADMIN"))
        safe(bot.send_message, call.message.chat.id,
             "📋 *QO'LDA POSTLAR TARIXI*\n\nHozircha post yo'q.", reply_markup=kb); return
    safe(bot.send_message, call.message.chat.id,
         "📋 *QO'LDA POSTLAR TARIXI*\n\nKerakli postni tanlang:",
         reply_markup=_mp_history_kb(uid))


@bot.callback_query_handler(func=lambda c: c.data == "MP_BACK_ADMIN")
def cb_mp_back_admin(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    safe(bot.send_message, call.message.chat.id, "⚙️ Admin panel", reply_markup=admin_kb(uid))


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("MPD_") and not c.data.startswith("MPDD_")
)
def cb_mpd(call):
    uid = call.from_user.id
    if not _can_mp_history(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    try:
        post_id = int(call.data[4:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Bu post sizga tegishli emas!", show_alert=True); return
    bot.answer_callback_query(call.id)
    cat  = f"\n🏷️ Tasnif: {post['category']}" if post.get("category") else ""
    age  = f"\n🔞 Yosh cheklov: {post['age_limit']}" if post.get("age_limit") else ""
    kind = _history_post_type_label(post.get("post_type"))
    media = "🖼️ Rasm" if post.get("image_id") else \
            ("🎬 Video" if post.get("video_id") else \
            ("🎙️ Ovoz" if post.get("audio_id") else "Yo'q"))
    deliveries = _mp_deliveries(post_id)
    delivery_lines = []
    for delivery in deliveries:
        delivery_lines.append(
            f"• {delivery.get('channel_name') or delivery.get('channel_id')} "
            f"(channel: `{delivery.get('channel_id')}`, message: "
            f"`{delivery.get('message_id') or '—'}`, {delivery.get('status')})"
        )
    delivery_text = "\n".join(delivery_lines) or "Hali kanalga yuborilmagan."
    short_text = str(post.get("text") or "")[:80]
    txt = (
        f"📄 *Post #{post['id']}*\n\n"
        f"📌 Turi: {kind}\n"
        f"📝 Matn: {short_text}\n"
        f"{cat}{age}\n"
        f"📎 Media: {media}\n"
        f"📡 Kanal xabarlari:\n{delivery_text}\n"
        f"📅 Yaratilgan: {str(post['created_at'])[:16]}"
    )
    safe(bot.send_message, call.message.chat.id, txt,
         reply_markup=_mp_detail_kb(post_id, uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPV_"))
def cb_mpv(call):
    uid = call.from_user.id
    if not _can_mp_history(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    try:
        post_id = int(call.data[4:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    _mp_preview_send(call.message.chat.id, post, f"👀 *Post #{post_id} ko'rinishi:*")
    safe(bot.send_message, call.message.chat.id,
         "📋 Post amallari:", reply_markup=_mp_detail_kb(post_id, uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPR_"))
def cb_mpr(call):
    uid = call.from_user.id
    if not _can_mp_repost(uid):
        bot.answer_callback_query(call.id, "❌ Qayta joylash ruxsati yo'q!", show_alert=True); return
    try:
        post_id = int(call.data[4:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if post.get("status") == "deleted":
        bot.answer_callback_query(call.id, "❌ O'chirilgan postni qayta joylab bo'lmaydi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    channels = get_autopost_channels(only_active=True)
    if not channels:
        bot.answer_callback_query(call.id, "❌ Faol avtopost kanallari yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    repost_draft = dict(post)
    repost_draft["post_id"] = post_id
    ok, fail = _mp_send_to_channels(repost_draft, uid)
    safe(bot.send_message, call.message.chat.id,
         f"🔁 *Qayta joylandi!*\n\n✅ Muvaffaqiyatli: *{ok}* kanal\n"
         f"❌ Xato: *{fail}* kanal\n\n{_mp_delivery_summary(post_id)}",
         reply_markup=_mp_detail_kb(post_id, uid))


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPDD_"))
def cb_mpdd(call):
    uid = call.from_user.id
    if not _can_mp_delete(uid):
        bot.answer_callback_query(call.id, "❌ O'chirish ruxsati yo'q!", show_alert=True); return
    try:
        post_id = int(call.data.rsplit("_", 1)[-1])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    if call.data == f"MPDD_{post_id}":
        bot.answer_callback_query(call.id)
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"MPDD_YES_{post_id}"),
            types.InlineKeyboardButton("❌ Yo'q", callback_data=f"MPDD_NO_{post_id}"),
        )
        safe(
            bot.send_message,
            call.message.chat.id,
            f"⚠️ *Post #{post_id} va uning kanallardagi xabarlarini o'chiraymi?*",
            reply_markup=kb,
        )
        return
    if call.data.startswith("MPDD_NO_"):
        bot.answer_callback_query(call.id, "Bekor qilindi")
        safe(bot.send_message, call.message.chat.id, "❌ O'chirish bekor qilindi.",
             reply_markup=_mp_detail_kb(post_id, uid))
        return
    if not call.data.startswith("MPDD_YES_"):
        bot.answer_callback_query(call.id, "❌ Noto'g'ri amal!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    deleted = _mp_delete_from_channels(post_id)
    if mp_delete(post_id):
        ok = sum(1 for _, success, _ in deleted if success)
        fail = len(deleted) - ok
        safe(
            bot.send_message,
            call.message.chat.id,
            f"✅ *Post #{post_id} o'chirildi.*\n\n"
            f"📡 Kanal xabarlari: {ok} ta o'chirildi, {fail} ta xato.",
            reply_markup=_mp_history_kb(uid),
        )
    else:
        safe(bot.send_message, call.message.chat.id, "❌ O'chirishda xato yuz berdi!")


@bot.callback_query_handler(
    func=lambda c: c.data.startswith("MPE_") and not c.data.startswith("MPEF_")
)
def cb_mpe(call):
    uid = call.from_user.id
    if not _can_mp_edit(uid):
        bot.answer_callback_query(call.id, "❌ Tahrirlash ruxsati yo'q!", show_alert=True); return
    try:
        post_id = int(call.data[4:])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Kanal matni", callback_data=f"MPEF_text_{post_id}"),
        types.InlineKeyboardButton("⛩️ Anime nomi", callback_data=f"MPEF_anime_title_{post_id}"),
        types.InlineKeyboardButton("🆕/📺 Post turi", callback_data=f"MPEF_post_type_{post_id}"),
        types.InlineKeyboardButton("📝 Tasnif", callback_data=f"MPEF_description_{post_id}"),
        types.InlineKeyboardButton("🎭 Janr", callback_data=f"MPEF_genres_{post_id}"),
        types.InlineKeyboardButton("📽️ Fasl", callback_data=f"MPEF_season_{post_id}"),
        types.InlineKeyboardButton("🎞️ Qismlar", callback_data=f"MPEF_episodes_{post_id}"),
        types.InlineKeyboardButton("🎙️ Ovoz", callback_data=f"MPEF_voice_{post_id}"),
        types.InlineKeyboardButton("🖼️ Rasm", callback_data=f"MPEF_image_{post_id}"),
        types.InlineKeyboardButton("🎬 Video", callback_data=f"MPEF_video_{post_id}"),
        types.InlineKeyboardButton("🎯 Holat", callback_data=f"MPEF_min_status_{post_id}"),
        types.InlineKeyboardButton("⚠️ Yosh cheklovi", callback_data=f"MPEF_age_{post_id}"),
        types.InlineKeyboardButton("🔑 Anime kodi", callback_data=f"MPEF_anime_code_{post_id}"),
        types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"MPD_{post_id}"),
    )
    safe(bot.send_message, call.message.chat.id,
         f"✏️ *Post #{post_id} tahrirlash*\n\nNimani tahrirlash?", reply_markup=kb)


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPEF_"))
def cb_mpef(call):
    uid = call.from_user.id
    if not _can_mp_edit(uid):
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    # MPEF_<field>_<post_id>
    rest = call.data[5:]  # e.g. "text_42" or "image_42"
    # split from right: post_id is the last segment
    parts = rest.rsplit("_", 1)
    if len(parts) != 2:
        bot.answer_callback_query(call.id, "❌ Xato!", show_alert=True); return
    field_key, post_id_str = parts
    try:
        post_id = int(post_id_str)
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Xato!", show_alert=True); return
    post = mp_get(post_id)
    if not post:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True); return
    if uid != OWNER_ID and post["created_by"] != uid:
        bot.answer_callback_query(call.id, "❌ Ruxsat yo'q!", show_alert=True); return
    bot.answer_callback_query(call.id)
    if field_key == "post_type":
        safe(
            bot.send_message,
            call.message.chat.id,
            "Post turini tanlang:",
            reply_markup=_mp_type_edit_kb(post_id),
        )
        return
    field_map = {
        "text":     "text",
        "post_type": "post_type",
        "category": "category",
        "image":    "image_id",
        "video":    "video_id",
        "audio":    "audio_id",
        "age":      "age_limit",
        "anime_title": "anime_title",
        "description": "description",
        "genres": "genres",
        "season": "season",
        "episodes": "episodes",
        "voice": "voice",
        "min_status": "min_status",
        "anime_code": "anime_code",
        "image": "image_id",
        "video": "video_id",
    }
    db_field = field_map.get(field_key, field_key)
    prompts = {
        "text":     "📝 Yangi matnni yozing:",
        "post_type": "🆕 Yangi anime yoki 📺 Yangi qism turini tanlang:",
        "category": "🏷️ Yangi tasnifni yozing (bo'sh — o'chirish):",
        "image":    "🖼️ Yangi rasmni yuboring:",
        "video":    "🎬 Yangi videoni yuboring:",
        "audio":    "🎙️ Yangi ovoz xabarini yuboring:",
        "age":      "🔞 Yangi yosh cheklovini yozing (bo'sh — o'chirish):",
        "anime_title": "⛩️ Yangi anime nomini yozing:",
        "description": "📝 Yangi tasnifni yozing (bo'sh — o'chirish):",
        "genres": "🎭 Yangi janrni yozing (bo'sh — o'chirish):",
        "season": "📽️ Yangi faslni yozing (bo'sh — o'chirish):",
        "episodes": "🎞️ Yangi qismlar sonini yozing (bo'sh — o'chirish):",
        "voice": "🎙️ Yangi ovozni yozing (bo'sh — o'chirish):",
        "min_status": "🎯 Yangi holatni yozing (bo'sh — o'chirish):",
        "anime_code": "🔑 Yangi anime kodini yozing:",
    }
    sset(uid, "mp_edit_field", {"post_id": post_id, "field": db_field})
    safe(bot.send_message, call.message.chat.id,
         prompts.get(field_key, "Yangi qiymatni yozing:\n_(bekor qilish: /cancel)_"))


@bot.callback_query_handler(func=lambda c: c.data.startswith("MPTYPE_"))
def cb_mp_type_edit(call):
    uid = call.from_user.id
    if not _can_mp_edit(uid):
        bot.answer_callback_query(call.id, "❌ Tahrirlash ruxsati yo'q!", show_alert=True)
        return
    # Callback formati: MPTYPE_new_anime_<id> yoki MPTYPE_new_episode_<id>.
    type_parts = call.data.split("_")
    if len(type_parts) != 4 or type_parts[1] != "new" or type_parts[2] not in {"anime", "episode"}:
        bot.answer_callback_query(call.id, "❌ Noto'g'ri post turi!", show_alert=True)
        return
    post_type = f"new_{type_parts[2]}"
    try:
        post_id = int(type_parts[3])
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True)
        return
    post = mp_get(post_id)
    if not post or (uid != OWNER_ID and post.get("created_by") != uid):
        bot.answer_callback_query(call.id, "❌ Post topilmadi!", show_alert=True)
        return
    if not mp_update(post_id, "post_type", post_type):
        bot.answer_callback_query(call.id, "❌ Post turi yangilanmadi!", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    result = _mp_sync_post(post_id)
    ok = sum(1 for _, success, _ in result if success)
    fail = len(result) - ok
    safe(
        bot.send_message,
        call.message.chat.id,
        f"✅ Post turi yangilandi: {_history_post_type_label(post_type)}\n"
        f"📡 Kanal xabarlari: {ok} ta yangilandi, {fail} ta xato.",
        reply_markup=_mp_detail_kb(post_id, uid),
    )


# ============================================================
#  UNIVERSAL HANDLER (holatlar + anime kodi)
# ============================================================

@bot.message_handler(content_types=["text","photo","video","document","animation","voice","audio"])
def h_universal(msg):
    uid = msg.from_user.id
    if not is_admin(uid) and not check_spam(uid):
        safe(bot.send_message, msg.chat.id, "⚠️ Iltimos, biroz kuting."); return
    if not is_admin(uid) and not check_sub(uid):
        chs = get_channels()
        if chs:
            safe(bot.send_message, msg.chat.id,
                "📢 *Botdan foydalanish uchun kanallarga obuna bo'ling:*\n\n"
                "Obuna bo'lgach ✅ *Tekshirish* tugmasini bosing.",
                reply_markup=sub_kb())
        return

    si = sget(uid); st = si.get("state",""); d = si.get("data",{})

    # ── FOYDALANUVCHI BOSHQARUVI ────────────────────────────────
    # ── UNIVERSAL MEDIA BO'LIMLARI ─────────────────────────────
    if st == "media_parts_code" and is_admin(uid) and msg.content_type == "text":
        media = _media_admin_lookup(msg.text)
        if not media:
            safe(
                bot.send_message, msg.chat.id,
                "❌ Media kodi yoki nomi topilmadi. Aniq kod yoki nomni yuboring:",
            )
            return
        sset(uid, "media_parts_menu", {"media_id": media["id"]})
        safe(
            bot.send_message, msg.chat.id,
            _media_admin_parts_text(media),
            reply_markup=_media_admin_parts_kb(media),
        )
        return

    if st == "media_part_season_wait" and is_admin(uid) and msg.content_type == "text":
        try:
            season_number = int(msg.text.strip())
            if season_number < 1:
                raise ValueError
        except (TypeError, ValueError):
            safe(bot.send_message, msg.chat.id, "❌ Fasl raqami 1 yoki undan katta bo'lsin.")
            return
        d["season_number"] = season_number
        sset(uid, "media_part_number_wait", d)
        safe(bot.send_message, msg.chat.id, "🔢 Bo'lim raqamini yuboring yoki `/skip` bosing:")
        return

    if st == "media_part_number_wait" and is_admin(uid) and msg.content_type == "text":
        try:
            part_number = int(msg.text.strip())
            if part_number < 1:
                raise ValueError
        except (TypeError, ValueError):
            safe(bot.send_message, msg.chat.id, "❌ Bo'lim raqami 1 yoki undan katta bo'lsin.")
            return
        d["part_number"] = part_number
        sset(uid, "media_part_file_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            f"📦 {part_number}-bo'lim faylini yuboring:\n"
            "Video, GIF, audio, voice, rasm yoki document qabul qilinadi.",
        )
        return

    if st == "media_part_file_wait" and is_admin(uid):
        file_id, file_type = _media_file_from_message(msg)
        if not file_id:
            safe(
                bot.send_message, msg.chat.id,
                "❌ Video, GIF, audio, voice, rasm yoki document yuboring.",
            )
            return
        ok, part_id = add_media_part(
            d.get("media_id"),
            d.get("part_type") or "part",
            file_id,
            file_type,
            d.get("season_number") or 1,
            d.get("part_number"),
            added_by=uid,
        )
        if not ok:
            safe(
                bot.send_message, msg.chat.id,
                "❌ Bu fasl va bo'lim raqami band yoki fayl saqlanmadi. "
                "Boshqa raqam yuboring:",
            )
            sset(uid, "media_part_number_wait", d)
            return
        media = get_media_item_by_id(d["media_id"]) or {}
        saved_number = int(d.get("part_number") or 1)
        part_type = d.get("part_type") or "part"
        season_number = int(d.get("season_number") or 1)
        threading.Thread(
            target=notify_new_episode,
            args=(media.get("code"), saved_number, part_type, season_number, part_type),
            daemon=True,
        ).start()
        next_number = next_media_part_number(
            d["media_id"], d.get("part_type") or "part", d.get("season_number") or 1,
        )
        d["part_number"] = next_number
        active_chs = get_autopost_channels(only_active=True)
        if _can_use_autopost(uid) and active_chs:
            sset(uid, "ap_ep_wait", {
                "anime_code": media.get("code"),
                "media_code": media.get("code"),
                "media_catalog_type": media.get("media_type"),
                "anime_title": media.get("title") or "Media",
                "ep_num": saved_number,
                "ep_type": part_type,
                "season_number": season_number,
            })
            safe(
                bot.send_message, msg.chat.id,
                f"✅ *{media.get('title') or 'Media'}* uchun "
                f"{season_number}-fasl, {saved_number}-bo'lim qo'shildi.\n\n"
                "📡 Kanalga posterli e'lon joylaysizmi?",
                reply_markup=_autopost_offer_kb(len(active_chs)),
            )
            return
        sset(uid, "media_part_file_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            f"✅ *{media.get('title') or 'Media'}* uchun "
            f"{season_number}-fasl, {saved_number}-bo'lim qo'shildi.\n\n"
            f"⬆️ Keyingi faylni yuboring — avtomatik raqam: *{next_number}*.\n"
            "Tugatish uchun admin panelga qayting.",
        )
        return

    # ── UNIVERSAL MEDIA TAHRIRI ────────────────────────────────
    if st == "media_edit_code" and is_admin(uid) and msg.content_type == "text":
        media = _media_admin_lookup(msg.text)
        if not media:
            safe(
                bot.send_message, msg.chat.id,
                "❌ Media kodi yoki nomi topilmadi. Aniq kod yoki nomni yuboring:",
            )
            return
        sset(uid, "media_edit_menu", dict(media))
        safe(
            bot.send_message, msg.chat.id,
            _media_edit_text(media),
            reply_markup=_media_edit_kb(),
        )
        return

    if st == "media_edit_field" and is_admin(uid):
        draft = dict(d.get("draft") or {})
        field = d.get("field")
        if field not in MEDIA_EDIT_FIELDS:
            sclear(uid)
            safe(bot.send_message, msg.chat.id, "❌ Tahrirlash maydoni topilmadi.")
            return
        if field == "poster_id":
            if msg.content_type != "photo":
                safe(bot.send_message, msg.chat.id, "❌ Poster uchun rasm yuboring.")
                return
            draft[field] = msg.photo[-1].file_id
        elif field == "main_media_id":
            file_id, file_type = _media_file_from_message(msg)
            if not file_id:
                safe(bot.send_message, msg.chat.id, "❌ Asosiy media faylini yuboring.")
                return
            draft[field] = file_id
            draft["main_media_type"] = file_type
        else:
            if msg.content_type != "text":
                safe(bot.send_message, msg.chat.id, "❌ Matn yuboring.")
                return
            value = msg.text.strip()
            if value == "-":
                value = None
            if field == "title" and not value:
                safe(bot.send_message, msg.chat.id, "❌ Media nomi bo'sh bo'lmasin.")
                return
            if field == "episode_total" and value not in (None, ""):
                if not str(value).isdigit() or int(value) < 0:
                    safe(bot.send_message, msg.chat.id, "❌ Bo'limlar sonini raqamda yuboring.")
                    return
                value = str(int(value))
            draft[field] = value
        sset(uid, "media_edit_menu", draft)
        safe(
            bot.send_message, msg.chat.id,
            _media_edit_text(draft),
            reply_markup=_media_edit_kb(),
        )
        return

# ── UNIVERSAL MEDIA O'CHIRISH ─────────────────────────────
    if st == "media_del_code" and is_admin(uid) and msg.content_type == "text":
        media = _media_admin_lookup(msg.text)
        if not media:
            safe(bot.send_message, msg.chat.id, "❌ Media kodi yoki nomi topilmadi.")
            return
        sset(uid, "media_del_confirm", {"code": media["code"], "title": media["title"]})
        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("✅ Ha, o'chirish", callback_data="MEDDEL_YES"),
            types.InlineKeyboardButton("❌ Bekor qilish", callback_data="MEDDEL_NO"),
        )
        safe(
            bot.send_message, msg.chat.id,
            f"⚠️ *{media['title']}* butunlay o'chiriladi.\n"
            "Media, uning bo'limlari va bog'langan ma'lumotlari bazadan o'chiriladi.\n\n"
            "Davom etishni tasdiqlaysizmi?",
            reply_markup=kb,
        )
        return

    # ── FOYDALANUVCHI BOSHQARUVI ────────────────────────────────
    if st == "user_manage_search" and is_admin(uid):
        if not admin_has_perm(uid, "user_manage"):
            sclear(uid)
            safe(bot.send_message, msg.chat.id, "❌ Sizda bu funksiyaga ruxsat yo'q.")
            return
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Telegram ID yoki @username yuboring.")
            return
        target_id = _find_user_by_input(msg.text.strip())
        user = get_user(target_id) if target_id else None
        if not user:
            safe(bot.send_message, msg.chat.id, "❌ Foydalanuvchi topilmadi. ID yoki @username ni tekshiring.")
            return
        sclear(uid)
        safe(bot.send_message, msg.chat.id, _user_manage_text(user),
             reply_markup=_user_manage_kb(user))
        return

    # ── MAVJUD ANIME AVTOPOSTI ────────────────────────────────
    if st in ("ap_existing_code_wait", "ap_existing_wait") and is_admin(uid) and msg.content_type == "text":
        _start_existing_anime_autopost(msg, msg.text.strip())
        return

    # ── TAYYOR POSTNI TAHRIRLASH ──────────────────────────────
    if st in ("ap_edit_text", "ap_edit_genres", "ap_edit_button"):
        draft = dict(d)
        return_state = draft.get("edit_return_state") or "ap_anime_wait"
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki bekor qilish uchun /cancel bosing.")
            return
        value = msg.text.strip()
        if not value:
            safe(bot.send_message, msg.chat.id, "❌ Bo'sh qiymat qabul qilinmaydi.")
            return
        if st == "ap_edit_text":
            draft["text"] = msg.text
        elif st == "ap_edit_genres":
            draft["genres"] = msg.text
            draft["text"] = _replace_post_genres(draft.get("text", ""), msg.text)
        else:
            if len(value) > 64:
                safe(bot.send_message, msg.chat.id, "❌ Tugma matni 64 belgidan qisqa bo'lsin.")
                return
            draft["button_text"] = value
        sset(uid, return_state, draft)
        safe(bot.send_message, msg.chat.id, "✅ Post nusxasi yangilandi.",
             reply_markup=_draft_keyboard(uid))
        return

    if st in ("ap_edit_photo", "ap_edit_video"):
        draft = dict(d)
        return_state = draft.get("edit_return_state") or "ap_anime_wait"
        if st == "ap_edit_photo":
            if msg.content_type != "photo":
                safe(bot.send_message, msg.chat.id, "❌ Rasm yuboring.")
                return
            draft["media_id"] = msg.photo[-1].file_id
            draft["media_type"] = "photo"
        else:
            if msg.content_type == "video":
                draft["media_id"] = msg.video.file_id
                draft["media_type"] = "video"
            elif msg.content_type == "animation":
                draft["media_id"] = msg.animation.file_id
                draft["media_type"] = "animation"
            elif msg.content_type == "document":
                draft["media_id"] = msg.document.file_id
                draft["media_type"] = "document"
            else:
                safe(bot.send_message, msg.chat.id, "❌ Qisqa video yuboring.")
                return
        sset(uid, return_state, draft)
        safe(bot.send_message, msg.chat.id, "✅ Media faqat shu post nusxasida almashtirildi.",
             reply_markup=_draft_keyboard(uid))
        return

    # ── QO'LDA POST YARATISH (9 bosqichli state machine) ─────
    if st == "mp_title_wait" and is_admin(uid) and msg.content_type == "text":
        value = msg.text.strip()
        if not value:
            safe(bot.send_message, msg.chat.id, "❌ Anime nomi bo'sh bo'lmasin.")
            return
        d["anime_title"] = value
        _mp_next_prompt(
            msg.chat.id, uid, "mp_description_wait", d,
            "2️⃣ *Qisqa tasnif/description* ni yozing:",
            "MP_SKIP_DESCRIPTION",
        )
        return

    if st == "mp_description_wait" and is_admin(uid) and msg.content_type == "text":
        d["description"] = msg.text.strip() or None
        _mp_next_prompt(
            msg.chat.id, uid, "mp_genres_wait", d,
            "3️⃣ *Janr yoki tasnif* ni yozing:",
            "MP_SKIP_GENRES",
        )
        return

    if st == "mp_genres_wait" and is_admin(uid) and msg.content_type == "text":
        d["genres"] = msg.text.strip() or None
        _mp_next_prompt(
            msg.chat.id, uid, "mp_season_wait", d,
            "4️⃣ *Fasl* sonini yozing (masalan: 3):",
            "MP_SKIP_SEASON",
        )
        return

    if st == "mp_season_wait" and is_admin(uid) and msg.content_type == "text":
        d["season"] = msg.text.strip() or None
        _mp_next_prompt(
            msg.chat.id, uid, "mp_episodes_wait", d,
            "5️⃣ *Qismlar* sonini yoki qo'shimcha qismlarni yozing:",
            "MP_SKIP_EPISODES",
        )
        return

    if st == "mp_episodes_wait" and is_admin(uid) and msg.content_type == "text":
        d["episodes"] = msg.text.strip() or None
        _mp_next_prompt(
            msg.chat.id, uid, "mp_voice_wait", d,
            "6️⃣ *Ovoz* turini yozing (masalan: O'zbekcha):",
            "MP_SKIP_VOICE",
        )
        return

    if st == "mp_voice_wait" and is_admin(uid) and msg.content_type == "text":
        d["voice"] = msg.text.strip() or None
        sset(uid, "mp_status_wait", d)
        safe(
            bot.send_message,
            msg.chat.id,
            "7️⃣ *Holat* ni tanlang yoki yozing (masalan: 🆓, Premium):",
            reply_markup=_mp_status_kb(),
        )
        return

    if st == "mp_status_wait" and is_admin(uid) and msg.content_type == "text":
        d["min_status"] = msg.text.strip() or None
        _mp_next_prompt(
            msg.chat.id, uid, "mp_age_wait", d,
            "8️⃣ *Yosh cheklovi* ni yozing (masalan: 13+):",
            "MP_SKIP_AGE",
        )
        return

    if st == "mp_age_wait" and is_admin(uid) and msg.content_type == "text":
        d["age_limit"] = msg.text.strip() or None
        sset(uid, "mp_media_wait", d)
        _mp_media_prompt(msg.chat.id)
        return

    if st == "mp_media_wait" and is_admin(uid):
        if msg.content_type == "photo":
            d["image_id"] = msg.photo[-1].file_id
            d["video_id"] = None
            d["audio_id"] = None
        elif msg.content_type == "video":
            d["image_id"] = None
            d["video_id"] = msg.video.file_id
            d["audio_id"] = None
        elif msg.content_type == "animation":
            d["image_id"] = None
            d["video_id"] = msg.animation.file_id
            d["audio_id"] = None
        elif msg.content_type == "document":
            d["image_id"] = None
            d["video_id"] = msg.document.file_id
            d["audio_id"] = None
        else:
            safe(
                bot.send_message,
                msg.chat.id,
                "❌ Rasm yoki qisqa video yuboring. "
                "Mediasiz davom etish uchun tugmani bosing.",
                reply_markup=_mp_media_kb(),
            )
            return
        sset(uid, "mp_code_wait", d)
        _mp_code_prompt(msg.chat.id)
        return

    if st == "mp_code_wait" and is_admin(uid) and msg.content_type == "text":
        code = msg.text.strip()
        if not code or not get_anime(code):
            safe(bot.send_message, msg.chat.id,
                 "❌ Bunday anime kodi topilmadi. Bazadagi kodni qayta yozing:")
            return
        d["anime_code"] = code
        d = _mp_draft_text(d)
        sset(uid, "mp_confirm_wait", d)
        _mp_preview_send(msg.chat.id, d)
        safe(bot.send_message, msg.chat.id,
             "✅ *Post tayyor!*\n\nTasdiqlashdan oldin Preview, Tahrirlash yoki "
             "Barcha faol kanallarga joylashni tanlang.",
             reply_markup=_mp_confirm_kb())
        return

    # Tasdiqlash holati (faqat qayta-preview uchun, tugmalar orqali ishlaydi)
    if st == "mp_confirm_wait" and is_admin(uid):
        return  # Tugmalar orqali boshqariladi

    # Preview ichidagi bitta maydonni tahrirlash.
    if st == "mp_draft_edit" and is_admin(uid):
        field = d.get("field")
        draft = dict(d.get("draft") or {})
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki /cancel bosing.")
            return
        value = msg.text.strip()
        if field == "anime_code" and not get_anime(value):
            safe(bot.send_message, msg.chat.id, "❌ Anime kodi bazada topilmadi. Qayta yozing:")
            return
        if field == "anime_title" and not value:
            safe(bot.send_message, msg.chat.id, "❌ Anime nomi bo'sh bo'lmasin.")
            return
        draft[field] = None if value == "-" else (value or None)
        draft = _mp_draft_text(draft)
        sset(uid, "mp_confirm_wait", draft)
        _mp_preview_send(msg.chat.id, draft)
        safe(bot.send_message, msg.chat.id, "✅ Draft yangilandi.",
             reply_markup=_mp_confirm_kb())
        return

    # Qo'lda post tahrirlash
    if st == "mp_edit_field" and is_admin(uid):
        post_id = d.get("post_id")
        field = d.get("field")
        if not post_id or not field:
            sclear(uid); return
        post = mp_get(post_id)
        if not post:
            safe(bot.send_message, msg.chat.id, "❌ Post topilmadi!"); sclear(uid); return
        val = None
        if field == "image_id":
            if msg.content_type == "photo":
                val = msg.photo[-1].file_id
            else:
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("❌ Bekor", callback_data=f"MPD_{post_id}"))
                safe(bot.send_message, msg.chat.id, "❌ Rasm yuboring:", reply_markup=kb); return
        elif field == "video_id":
            if msg.content_type == "video":
                val = msg.video.file_id
            elif msg.content_type == "animation":
                val = msg.animation.file_id
            elif msg.content_type == "document":
                val = msg.document.file_id
            else:
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("❌ Bekor", callback_data=f"MPD_{post_id}"))
                safe(bot.send_message, msg.chat.id, "❌ Video yuboring:", reply_markup=kb); return
        elif field == "audio_id":
            if msg.content_type == "voice":
                val = msg.voice.file_id
            elif msg.content_type == "audio":
                val = msg.audio.file_id
            else:
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("❌ Bekor", callback_data=f"MPD_{post_id}"))
                safe(bot.send_message, msg.chat.id, "❌ Ovoz xabari yuboring:", reply_markup=kb); return
        elif msg.content_type == "text":
            val = msg.text.strip()
            if field == "anime_title" and not val:
                safe(bot.send_message, msg.chat.id, "❌ Anime nomi bo'sh bo'lmasin."); return
            if field == "anime_code" and val and not get_anime(val):
                safe(bot.send_message, msg.chat.id,
                     "❌ Anime kodi bazada topilmadi. Qayta yozing:"); return
            val = None if val in ("", "-") else val
        else:
            kb = types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("❌ Bekor", callback_data=f"MPD_{post_id}"))
            safe(bot.send_message, msg.chat.id, "❌ Noto'g'ri format!", reply_markup=kb); return
        if not mp_update(post_id, field, val):
            safe(bot.send_message, msg.chat.id, "❌ Post yangilanmadi."); sclear(uid); return
        sync_result = _mp_sync_post(
            post_id,
            force_replace=field in {"image_id", "video_id", "audio_id"},
        )
        sclear(uid)
        synced = sum(1 for _, success, _ in sync_result if success)
        sync_failed = len(sync_result) - synced
        safe(bot.send_message, msg.chat.id,
             f"✅ Post #{post_id} muvaffaqiyatli yangilandi!\n\n"
             f"📡 Kanal xabarlari: {synced} ta yangilandi, {sync_failed} ta xato.",
             reply_markup=_mp_detail_kb(post_id, uid))
        return

    # ── UNIVERSAL MEDIA QO'SHISH ──────────────────────────────
    if st == "media_poster_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "photo":
            safe(bot.send_message, msg.chat.id, "❌ Rasm yuboring yoki `/skip` bosing.")
            return
        d["poster_id"] = msg.photo[-1].file_id
        sset(uid, "media_description_wait", d)
        safe(bot.send_message, msg.chat.id, "2️⃣ Media tavsifini yozing yoki `/skip` bosing:")
        return

    if st == "media_description_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki `/skip` bosing.")
            return
        d["description"] = msg.text.strip() or None
        sset(uid, "media_genres_wait", d)
        safe(bot.send_message, msg.chat.id, "3️⃣ Janr yoki tasnifni yozing yoki `/skip` bosing:")
        return

    if st == "media_genres_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki `/skip` bosing.")
            return
        d["genres"] = msg.text.strip() or None
        sset(uid, "media_season_wait", d)
        safe(bot.send_message, msg.chat.id, "4️⃣ Fasl ma'lumotini yozing yoki `/skip` bosing:")
        return

    if st == "media_season_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki `/skip` bosing.")
            return
        d["season"] = msg.text.strip() or None
        sset(uid, "media_episode_wait", d)
        safe(bot.send_message, msg.chat.id, "5️⃣ Qismlar sonini yozing yoki `/skip` bosing:")
        return

    if st in ("media_episode_wait", "media_episodes_wait") and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki `/skip` bosing.")
            return
        d["episode_total"] = msg.text.strip() or None
        sset(uid, "media_voice_wait", d)
        safe(bot.send_message, msg.chat.id, "6️⃣ Ovoz/dublyajni yozing yoki `/skip` bosing:")
        return

    if st == "media_voice_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Matn yuboring yoki `/skip` bosing.")
            return
        d["voice"] = msg.text.strip() or None
        sset(uid, "media_status_wait", d)
        safe(
            bot.send_message, msg.chat.id,
            "7️⃣ Media uchun kirish darajasini tanlang:",
            reply_markup=_media_status_kb(),
        )
        return

    if st == "media_age_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Yosh cheklovini matn ko'rinishida yuboring yoki `/skip` bosing.")
            return
        d["age_limit"] = msg.text.strip() or None
        sset(uid, "media_main_media_wait", d)
        safe(bot.send_message, msg.chat.id, "🔟 Asosiy media faylini yuboring yoki `/skip` bosing:")
        return

    if st in ("media_main_media_wait", "media_main_wait") and is_admin(uid) and admin_has_perm(uid, "add_media"):
        media_fields = {
            "photo": (getattr(msg, "photo", None), "photo"),
            "video": (getattr(msg, "video", None), "video"),
            "animation": (getattr(msg, "animation", None), "animation"),
            "document": (getattr(msg, "document", None), "document"),
            "audio": (getattr(msg, "audio", None), "audio"),
            "voice": (getattr(msg, "voice", None), "voice"),
        }
        item, media_type = media_fields.get(msg.content_type, (None, None))
        if not item:
            safe(
                bot.send_message, msg.chat.id,
                "❌ Rasm, video, GIF, fayl, audio yoki voice yuboring. "
                "Mediasiz davom etish uchun `/skip` bosing.",
            )
            return
        d["main_media_id"] = item[-1].file_id if media_type == "photo" else item.file_id
        d["main_media_type"] = media_type
        d["code"] = next_content_code()
        sset(uid, "media_title_wait", d)
        safe(
            bot.send_message,
            msg.chat.id,
            f"🔢 Avtomatik kod: `{d['code']}`\n"
            "1️⃣1️⃣ Media nomini yozing:",
        )
        return

    if st == "media_code_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        # Eski sessiyalar uchun moslik: endi kod hech qachon qo'lda olinmaydi.
        d["code"] = next_content_code()
        sset(uid, "media_title_wait", d)
        safe(
            bot.send_message,
            msg.chat.id,
            f"🔢 Avtomatik kod: `{d['code']}`\n"
            "1️⃣1️⃣ Media nomini yozing:",
        )
        return

    if st == "media_title_wait" and is_admin(uid) and admin_has_perm(uid, "add_media"):
        if msg.content_type != "text":
            safe(bot.send_message, msg.chat.id, "❌ Media nomini matn ko'rinishida yuboring.")
            return
        title = msg.text.strip()
        if not title:
            safe(bot.send_message, msg.chat.id, "❌ Media nomi bo'sh bo'lmasin:")
            return
        d["code"] = d.get("code") or next_content_code()
        d["title"] = title
        sset(uid, "media_confirm_wait", d)
        safe(bot.send_message, msg.chat.id, _media_form_preview(d), reply_markup=_media_confirm_kb())
        return

    # ── QISMNI TAHRIRLASH — yangi fayl ───────────────────────
    if st == "ep_edit_file" and is_admin(uid):
        if msg.content_type == "video":
            fid = msg.video.file_id; ftype = "video"
        elif msg.content_type == "animation":
            fid = msg.animation.file_id; ftype = "animation"
        elif msg.content_type == "document":
            fid = msg.document.file_id; ftype = "document"
        else:
            safe(bot.send_message, msg.chat.id, "❌ Video, GIF yoki fayl yuboring!"); return
        code = d["anime_code"]; num = d["ep_num"]; etype = d["ep_type"]
        con2 = db(); c2 = con2.cursor()
        c2.execute(
            "UPDATE episodes SET file_id=?, file_type=? WHERE anime_code=? AND ep_num=? AND ep_type=?",
            (fid, ftype, code, num, etype)
        )
        con2.commit(); con2.close()
        sclear(uid)
        tname = "OVA" if etype == "ova" else "Asosiy"
        kb2 = types.InlineKeyboardMarkup()
        kb2.add(types.InlineKeyboardButton("🔙 Qism sozlamalariga", callback_data=f"QSM_{code}"))
        safe(bot.send_message, msg.chat.id,
            f"✅ *{d['anime_title']}* — {tname} {num}-qism yangilandi!",
            reply_markup=kb2); return

    # ── QISM QO'SHISH ─────────────────────────────────────────
    if st == "ep_code" and is_admin(uid) and msg.content_type == "text":
        a = get_anime(msg.text.strip())
        if not a:
            safe(bot.send_message, msg.chat.id, "❌ Anime topilmadi. Kodni tekshiring."); return
        d["anime_code"] = a["code"]; d["anime_title"] = a["title"]
        sset(uid, "ep_type", d)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📺 Asosiy (Season)", callback_data="EPT_season"),
               types.InlineKeyboardButton("🎞️ OVA", callback_data="EPT_ova"))
        safe(bot.send_message, msg.chat.id, f"🎬 *{a['title']}*\n\nQism turini tanlang:", reply_markup=kb); return

    # Qism qo'shish rejimi avtopost taklifi ko'rsatilganda ham yopilmaydi.
    # Shu sababli keyingi video `ap_ep_wait` holatida ham qabul qilinadi;
    # callback tugmalari esa o'zining avtopost oqimida ishlashda davom etadi.
    if st in ("ep_file", "ap_ep_wait") and is_admin(uid):
        if msg.content_type == "video":
            fid = msg.video.file_id; ftype = "video"
        elif msg.content_type == "animation":
            fid = msg.animation.file_id; ftype = "animation"
        elif msg.content_type == "document":
            fid = msg.document.file_id; ftype = "document"
        else:
            safe(bot.send_message, msg.chat.id, "❌ Video, GIF yoki fayl yuboring!"); return

        mgid = getattr(msg, "media_group_id", None)

        if mgid:
            with MG_LOCK:
                if mgid not in MEDIA_GROUPS:
                    MEDIA_GROUPS[mgid] = {
                        "uid": uid,
                        "chat_id": msg.chat.id,
                        "files": [],
                        "data": dict(d),
                    }
                MEDIA_GROUPS[mgid]["files"].append((fid, ftype))
                old_timer = MEDIA_GROUPS[mgid].get("timer")
                if old_timer:
                    old_timer.cancel()
                t = threading.Timer(3.0, _process_media_group, args=(mgid,))
                MEDIA_GROUPS[mgid]["timer"] = t
                t.start()
        else:
            code = d["anime_code"]; et = d["ep_type"]
            nn = next_ep_num(code, et)
            if add_ep(code, nn, et, fid, ftype):
                log_admin_action(uid, "episode_added", code, et, nn)
                threading.Thread(
                    target=notify_new_episode,
                    args=(code, nn, et),
                    daemon=True,
                ).start()
                tname = "OVA" if et == "ova" else "Asosiy"
                total_now = ep_count(code, et)
                # Avtopost taklifi
                active_chs = get_autopost_channels(only_active=True)
                if _can_use_autopost(uid) and active_chs:
                    sset(uid, "ap_ep_wait", {
                        "anime_code": code,
                        "anime_title": d["anime_title"],
                        "ep_num": nn,
                        "ep_type": et,
                    })
                    safe(bot.send_message, msg.chat.id,
                        f"✅ *Yangi qism muvaffaqiyatli qo'shildi!*\n\n"
                        f"🎬 Anime: *{d['anime_title']}*\n"
                        f"📹 Tur: *{tname}*\n"
                        f"🔢 Qism: *{nn}*\n"
                        f"📊 Jami bazada: *{total_now}* ta qism\n\n"
                        f"📡 *Kanalga e'lon joylaysizmi?*",
                        reply_markup=_autopost_offer_kb(len(active_chs)))
                else:
                    safe(bot.send_message, msg.chat.id,
                        f"✅ *Qism qo'shildi!*\n\n🎬 Anime: *{d['anime_title']}*\n"
                        f"📹 Tur: *{tname}*\n🔢 Qism: *{nn}*\n"
                        f"📊 Jami bazada: *{total_now}* ta qism\n\n"
                        f"⬆️ Yana fayl yuboring — davom ettiradi.\n"
                        f"Tugatish uchun '🔙 Orqaga' ni bosing.")
            else:
                safe(bot.send_message, msg.chat.id, "❌ Xato yuz berdi!")
        return

    # ── BROADCAST ──────────────────────────────────────────────
    if st == "bc_msg" and is_admin(uid):
        d["msg_id"] = msg.message_id; d["from_chat"] = msg.chat.id
        sset(uid, "bc_confirm", d)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📤 Yuborish", callback_data="BC_SEND"),
               types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="BC_EDIT"),
               types.InlineKeyboardButton("❌ Bekor", callback_data="BC_CANCEL"))
        safe(bot.send_message, msg.chat.id, "📢 *Broadcast ko'rinishi:*")
        try: bot.forward_message(msg.chat.id, msg.chat.id, msg.message_id)
        except Exception: pass
        safe(bot.send_message, msg.chat.id, "Tasdiqlaysizmi?", reply_markup=kb); return

    # ── ADMIN QO'SHISH ─────────────────────────────────────────
    if st == "adm_add" and uid == OWNER_ID and msg.content_type == "text":
        try:
            new_id = int(msg.text.strip())
            if add_admin(new_id, uid):
                sclear(uid)
                safe(bot.send_message, msg.chat.id, f"✅ `{new_id}` admin qo'shildi!", reply_markup=admin_kb(uid))
                try: bot.send_message(new_id, "🔧 *Sizga admin huquqi berildi!*\n\n/start bosing.")
                except Exception: pass
            else:
                safe(bot.send_message, msg.chat.id, "❌ Bu foydalanuvchi allaqachon admin!")
        except ValueError:
            safe(bot.send_message, msg.chat.id, "❌ Noto'g'ri ID! Faqat raqam yozing.")
        return

    # ── PREMIUM BERISH ─────────────────────────────────────────
    if st == "give_prem" and uid == OWNER_ID and msg.content_type == "text":
        tid = _find_user_by_input(msg.text.strip())
        if tid:
            give_premium(tid); sclear(uid)
            safe(bot.send_message, msg.chat.id, f"✅ `{tid}` ga 💎 Premium berildi (30 kun)!", reply_markup=admin_kb(uid))
            try:
                bot.send_message(tid,
                    "💎 *Tabriklaymiz! Sizga Premium status berildi!*\n\nMuddat: 30 kun\n\n"
                    "✨ *Premium imtiyozlar:*\n"
                    "• Majburiy obunasiz foydalanish\n"
                    "• Barcha maxsus animeler\n"
                    "• Kelajakdagi premium funksiyalar")
            except Exception: pass
        else:
            safe(bot.send_message, msg.chat.id, "❌ Foydalanuvchi topilmadi!")
        return

    # ── VIP BERISH ─────────────────────────────────────────────
    if st == "give_vip" and uid == OWNER_ID and msg.content_type == "text":
        tid = _find_user_by_input(msg.text.strip())
        if tid:
            _give_vip(tid, auto=False)
            sclear(uid)
            safe(bot.send_message, msg.chat.id, f"✅ `{tid}` ga ⭐ VIP berildi (30 kun)!", reply_markup=admin_kb(uid))
            try:
                bot.send_message(tid,
                    "⭐ *Tabriklaymiz! Sizga VIP status berildi!*\n\nMuddat: 30 kun\n\n"
                    "✨ *VIP imtiyozlar:*\n"
                    "• Eksklyuziv VIP animeler\n"
                    "• Maxsus kontent\n")
            except Exception: pass
        else:
            safe(bot.send_message, msg.chat.id, "❌ Foydalanuvchi topilmadi!")
        return

    # ── STATUS O'CHIRISH ───────────────────────────────────────
    if st == "remove_status" and uid == OWNER_ID and msg.content_type == "text":
        tid = _find_user_by_input(msg.text.strip())
        if tid:
            u = get_user(tid)
            if not u:
                safe(bot.send_message, msg.chat.id, "❌ Foydalanuvchi topilmadi!"); return
            old_st = u.get("status", "user")
            remove_status(tid); sclear(uid)
            safe(bot.send_message, msg.chat.id,
                f"✅ `{tid}` foydalanuvchining *{ST_NAME.get(old_st, old_st)}* statusi o'chirildi!",
                reply_markup=admin_kb(uid))
            try:
                bot.send_message(tid,
                    f"⚠️ *{ST_NAME.get(old_st, old_st)} statusingiz o'chirildi.*\n\nAdmin tomonidan bekor qilindi.")
            except Exception: pass
        else:
            safe(bot.send_message, msg.chat.id, "❌ Foydalanuvchi topilmadi!")
        return

    # ── MAJBURIY OBUNA KANAL QO'SHISH (faqat Owner) ──────────
    if st == "ch_tg_waiting" and uid == OWNER_ID and msg.content_type == "text":
        raw = msg.text.strip()
        if raw.startswith("https://t.me/"):
            cid = "@" + raw.split("https://t.me/")[1].rstrip("/")
        elif raw.startswith("t.me/"):
            cid = "@" + raw.split("t.me/")[1].rstrip("/")
        elif raw.startswith("@"):
            cid = raw
        else:
            cid = "@" + raw
        try:
            chat_info = bot.get_chat(cid)
            ch_name = chat_info.title or cid
            ch_url = f"https://t.me/{chat_info.username}" if getattr(chat_info, "username", None) else f"https://t.me/c/{str(chat_info.id)[4:]}"
            real_id = str(chat_info.id)
            if add_channel(real_id, ch_name, ch_url, 'telegram'):
                sclear(uid)
                safe(bot.send_message, msg.chat.id, f"✅ Telegram kanal qo'shildi: *{ch_name}*", reply_markup=admin_kb(uid))
            else:
                sclear(uid)
                safe(bot.send_message, msg.chat.id, "❌ Bu kanal allaqachon mavjud!", reply_markup=admin_kb(uid))
        except Exception as e:
            logger.error("Majburiy obuna kanalini tekshirish xatosi: %s", e)
            safe(bot.send_message, msg.chat.id, f"❌ Kanal topilmadi: `{e}`\n\nQaytadan yuboring yoki /cancel deb yozing.")
        return

    if st == "ch_ig_waiting" and uid == OWNER_ID and msg.content_type == "text":
        raw = msg.text.strip()
        if "instagram.com/" in raw:
            username = raw.rstrip("/").split("/")[-1].lstrip("@")
            url = f"https://instagram.com/{username}"
        elif raw.startswith("@"):
            username = raw.lstrip("@")
            url = f"https://instagram.com/{username}"
        else:
            username = raw.lstrip("@")
            url = f"https://instagram.com/{username}"
        ch_name = f"@{username}"
        cid = f"ig_{username}"
        if add_channel(cid, ch_name, url, 'instagram'):
            sclear(uid)
            safe(bot.send_message, msg.chat.id, f"✅ Instagram profil qo'shildi: *{ch_name}*", reply_markup=admin_kb(uid))
        else:
            sclear(uid)
            safe(bot.send_message, msg.chat.id, "❌ Bu profil allaqachon mavjud!", reply_markup=admin_kb(uid))
        return

    if st == "ch_yt_waiting" and uid == OWNER_ID and msg.content_type == "text":
        raw = msg.text.strip()
        if "youtube.com/" in raw or "youtu.be/" in raw:
            parts = raw.rstrip("/").split("/")
            ch_name = parts[-1].lstrip("@") or "YouTube"
            url = raw if raw.startswith("http") else f"https://youtube.com/{raw}"
        else:
            ch_name = raw.lstrip("@")
            url = f"https://youtube.com/@{ch_name}"
        cid = f"yt_{ch_name}"
        if add_channel(cid, ch_name, url, 'youtube'):
            sclear(uid)
            safe(bot.send_message, msg.chat.id, f"✅ YouTube kanal qo'shildi: *{ch_name}*", reply_markup=admin_kb(uid))
        else:
            sclear(uid)
            safe(bot.send_message, msg.chat.id, "❌ Bu kanal allaqachon mavjud!", reply_markup=admin_kb(uid))
        return

    # ── AVTOPOST KANAL QO'SHISH ───────────────────────────────
    if st == "aps_ch_id" and uid == OWNER_ID and msg.content_type == "text":
        cid = msg.text.strip()
        # Kanal va bot huquqini tekshirish
        try:
            chat_info = bot.get_chat(cid)
            # Bot admin ekanligini tekshirish
            bot_member = bot.get_chat_member(chat_info.id, bot.get_me().id)
            if bot_member.status not in ("administrator", "creator"):
                safe(
                    bot.send_message,
                    msg.chat.id,
                    "❌ *Bot ushbu kanalga post joylay olmaydi.*\n\n"
                    "Botni kanalga admin qiling va unga xabar/post joylash ruxsatini bering.",
                )
                return
            # Post yuborish ruxsatini tekshirish
            if bot_member.status == "administrator" and hasattr(bot_member, "can_post_messages"):
                if not bot_member.can_post_messages:
                    safe(
                        bot.send_message,
                        msg.chat.id,
                        "❌ *Bot kanalga post joylay olmaydi.*\n\n"
                        "Botga kanalda *Xabar yuborish* ruxsatini bering.",
                    )
                    return
            ch_name = chat_info.title or cid
            ch_url = f"https://t.me/{chat_info.username}" if getattr(chat_info, "username", None) else f"t.me/c/{str(chat_info.id)[4:]}"
            real_id = str(chat_info.id)
            if add_autopost_channel(real_id, ch_name, ch_url):
                sclear(uid)
                safe(bot.send_message, msg.chat.id,
                    f"✅ *Avtopost kanali muvaffaqiyatli qo'shildi!*\n\n"
                    f"📡 Kanal: *{ch_name}*\n"
                    f"🟢 Holat: Yoqilgan",
                    reply_markup=_autopost_menu_kb())
            else:
                safe(bot.send_message, msg.chat.id, "❌ Bu kanal allaqachon avtopost ro'yxatida mavjud!")
        except Exception as e:
            logger.error("Avtopost kanalini tekshirish xatosi: %s", e)
            safe(bot.send_message, msg.chat.id,
                f"❌ *Bot ushbu kanalga post joylay olmaydi.*\n\n"
                f"Botni kanalga admin qiling va unga xabar/post joylash ruxsatini bering.\n\n"
                "Qaytadan urinib ko'ring yoki /cancel deb yozing.")
        return

    # ── AVTOPOST TUGMA MATNI ──────────────────────────────────
    if st == "aps_btn_text" and uid == OWNER_ID and msg.content_type == "text":
        new_text = msg.text.strip()
        if len(new_text) > 64:
            safe(bot.send_message, msg.chat.id, "❌ Matn juda uzun! 64 belgidan qisqa yozing."); return
        set_autopost_setting("watch_btn_text", new_text)
        sclear(uid)
        safe(bot.send_message, msg.chat.id,
            f"✅ Tugma matni o'zgartirildi!\n\nYangi matn: *{new_text}*",
            reply_markup=_autopost_menu_kb())
        return

    # ── AVTOPOST KANAL QATORI ──────────────────────────────────
    if st == "aps_main_tag" and uid == OWNER_ID and msg.content_type == "text":
        new_tag = msg.text.strip()
        set_autopost_setting(
            "main_channel_tag",
            DEFAULT_CHANNEL_TAG if new_tag in ("", "-") else new_tag,
        )
        sclear(uid)
        safe(
            bot.send_message,
            msg.chat.id,
            f"✅ Kanal qatori yangilandi!\n\n📡 {get_main_channel_tag()}",
            reply_markup=_autopost_menu_kb(),
        )
        return

    # ── BACKUP TIKLASH — JSON FAYL ────────────────────────────
    if st == "bkp_file_wait" and uid == OWNER_ID:
        if msg.content_type != "document":
            safe(bot.send_message, msg.chat.id,
                "❌ JSON faylini yuboring.\n_(bekor qilish: /cancel)_"); return
        try:
            file_info = bot.get_file(msg.document.file_id)
            downloaded = bot.download_file(file_info.file_path)
            backup_data = json.loads(downloaded.decode("utf-8"))
            if "data" not in backup_data or "backup_version" not in backup_data:
                safe(bot.send_message, msg.chat.id,
                    "❌ *Backup fayli noto'g'ri yoki buzilgan.*\n\nFaqat ANIBEST backup fayllarini yuklang.")
                return
            sset(uid, "bkp_confirm", {"backup_data": backup_data})
            stats = backup_data.get("stats", {})
            backup_rows = backup_data.get("data", {})
            media_count = len(backup_rows.get("media_items", []))
            category_count = len(backup_rows.get("media_categories", []))
            kb_confirm = types.InlineKeyboardMarkup(row_width=1)
            kb_confirm.add(
                types.InlineKeyboardButton("✅ Ha, tiklash", callback_data="BKP_RESTORE_YES"),
                types.InlineKeyboardButton("❌ Bekor qilish", callback_data="BKP_RESTORE_NO"),
            )
            safe(bot.send_message, msg.chat.id,
                f"⚠️ *Diqqat!*\n\n"
                f"Backupni tiklash hozirgi ma'lumotlarni almashtirishi mumkin.\n\n"
                f"📦 *Backup ma'lumotlari:*\n"
                f"📅 Sana: `{backup_data.get('created_at','—')}`\n"
                f"👥 Foydalanuvchilar: *{stats.get('users',0)}*\n"
                f"🎬 Animeler: *{stats.get('animes',0)}*\n"
                f"📹 Qismlar: *{stats.get('episodes',0)}*\n"
                f"🎞️ Universal media: *{media_count}* ta\n"
                f"📚 Media kategoriyalari: *{category_count}* ta\n\n"
                f"ℹ️ Eski backup bo'lsa, standart media kategoriyalari qayta yaratiladi "
                f"va anime katalogga mirror qilinadi.\n\n"
                f"Davom etasizmi?",
                reply_markup=kb_confirm)
        except json.JSONDecodeError:
            safe(bot.send_message, msg.chat.id, "❌ *Backup fayli noto'g'ri yoki buzilgan.*")
        except Exception as e:
            logger.error(f"Backup fayl o'qish: {e}")
            safe(bot.send_message, msg.chat.id,
                "❌ Backup faylini o'qishda xato yuz berdi. JSON faylini tekshiring.")
        return

    # ── QIDIRUV ────────────────────────────────────────────────
    if st == "media_searching" and msg.content_type == "text":
        sclear(uid)
        q = msg.text.strip()
        direct = get_media_item(q)
        if direct:
            show_media_item(msg.chat.id, uid, direct["id"])
            return
        results = search_media(q)
        if not results:
            safe(bot.send_message, msg.chat.id, f"❌ *'{q}'* bo'yicha hech narsa topilmadi.")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for media in results:
            kb.add(types.InlineKeyboardButton(
                f"{media_type_icon(media.get('media_type'))} "
                f"{(media.get('title') or media.get('code') or 'Media')[:42]}",
                callback_data=f"MED_OPEN|{media['id']}",
            ))
        safe(
            bot.send_message, msg.chat.id,
            f"🔍 *'{q}'* bo'yicha media natijalari:\n\nMedia tanlang:",
            reply_markup=kb,
        )
        return

    if st == "searching" and msg.content_type == "text":
        sclear(uid)
        q = msg.text.strip()
        if get_anime(q):
            show_anime(msg.chat.id, uid, q); return
        res = search_anime(q)
        if not res:
            safe(bot.send_message, msg.chat.id, f"❌ *'{q}'* bo'yicha hech narsa topilmadi."); return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for a in res:
            kb.add(types.InlineKeyboardButton(
                f"🎬 {(a.get('title') or a.get('code') or 'Anime')[:45]}",
                callback_data=f"ANID_{a['id']}",
            ))
        safe(bot.send_message, msg.chat.id,
             f"🔍 *'{q}'* bo'yicha natijalar:\n\nAnimeni tanlang:",
             reply_markup=kb)
        return

    # ── ANIME KODI ─────────────────────────────────────────────
    if msg.content_type == "text":
        code = msg.text.strip()
        if code and len(code) <= 64 and not code.startswith("/"):
            anime = get_anime(code)
            if anime:
                show_anime(msg.chat.id, uid, code)
                return
            media = get_media_item(code)
            if media:
                show_media_item(msg.chat.id, uid, media["id"])
                return
            safe(bot.send_message, msg.chat.id, "❌ Bunday media topilmadi.")


# ============================================================
#  MUDDAT TEKSHIRGICH
# ============================================================

def expiry_loop():
    while True:
        try:
            now = local_now().strftime("%Y-%m-%d %H:%M:%S")
            con = db(); c = con.cursor()
            c.execute("SELECT user_id FROM users WHERE status='vip' AND vip_expires IS NOT NULL AND vip_expires<=?", (now,))
            ev = [r["user_id"] for r in c.fetchall()]
            c.execute("SELECT user_id FROM users WHERE status='premium' AND premium_expires IS NOT NULL AND premium_expires<=?", (now,))
            ep = [r["user_id"] for r in c.fetchall()]
            con.close()
            for uid in ev: _expire(uid, "vip")
            for uid in ep: _expire(uid, "premium")
        except Exception as e:
            logger.error(f"expiry loop: {e}")
        time.sleep(3600)


# ============================================================
#  MAIN
# ============================================================

def run_polling():
    """Telegram API uzilsa, exponential backoff kutmasdan qayta ulaydi."""
    first_poll = True
    while True:
        try:
            # infinity_polling ichki xatoliklarda 60 soniyagacha backoff qiladi.
            # Oddiy polling + tashqi sikl esa internet qaytgach 1 soniya ichida
            # yangi ulanishni boshlaydi va update'larni tashlab yubormaydi.
            bot.polling(
                non_stop=False,
                interval=0,
                timeout=10,
                long_polling_timeout=5,
                skip_pending=first_poll,
                logger_level=logging.WARNING,
            )
        except KeyboardInterrupt:
            logger.info("Polling to'xtatildi.")
            return
        except Exception as exc:
            logger.warning(
                "Telegram API vaqtincha ulanmayapti; 1 soniyadan keyin qayta uriniladi: %s",
                type(exc).__name__,
            )
        finally:
            # Qayta ulanishda pending update'lar tashlab yuborilmasin.
            first_poll = False
        time.sleep(1)


if __name__ == "__main__":
    logger.info("🎬 ANIBEST BOT ishga tushmoqda...")
    init_db()
    threading.Thread(target=expiry_loop, daemon=True).start()
    logger.info("⏰ Muddat tekshirgich ishga tushdi")
    try:
        me = bot.get_me()
        BOT_USERNAME = me.username or ""
        logger.info(f"🤖 Bot: @{BOT_USERNAME} | Owner: {OWNER_ID}")
    except Exception as e:
        logger.error(f"Bot ma'lumotlari: {e}")
    logger.info("✅ Polling boshlandi...")
    run_polling()
