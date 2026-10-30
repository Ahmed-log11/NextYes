"""Sector archetypes for synthetic businesses.

Ranges are plausible illustrations for a demo, not market statistics.
Every healthy business is generated with annual revenue above SAR 2M so it
passes both lender policies before any issue is planted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sector:
    key: str
    label_en: str
    label_ar: str
    monthly_revenue_sar: tuple[int, int]
    operating_margin: tuple[float, float]
    seasonality: tuple[float, ...]  # 12 multipliers, Jan..Dec, mean ≈ 1
    name_suffix_en: str
    name_suffix_ar: str


SECTORS: tuple[Sector, ...] = (
    Sector("food_supply", "Food & beverage supply", "توريد أغذية ومشروبات",
           (180_000, 420_000), (0.14, 0.22),
           (0.95, 0.95, 1.05, 1.15, 1.0, 0.9, 0.9, 0.95, 1.0, 1.0, 1.05, 1.1),
           "Food Supplies", "لتوريد الأغذية"),
    Sector("construction", "Construction contracting", "مقاولات",
           (250_000, 900_000), (0.10, 0.18),
           (1.0, 1.05, 1.1, 1.0, 0.95, 0.85, 0.8, 0.9, 1.05, 1.1, 1.1, 1.1),
           "Contracting", "للمقاولات"),
    Sector("ecommerce", "E-commerce retail", "تجارة إلكترونية",
           (180_000, 500_000), (0.12, 0.24),
           (0.9, 0.85, 0.95, 1.1, 0.95, 0.9, 0.9, 0.95, 1.0, 1.05, 1.25, 1.2),
           "Online Store", "للتجارة الإلكترونية"),
    Sector("logistics", "Logistics and delivery", "خدمات لوجستية وتوصيل",
           (200_000, 600_000), (0.12, 0.20),
           (1.0, 0.95, 1.0, 1.1, 1.0, 0.95, 0.9, 0.95, 1.0, 1.0, 1.05, 1.1),
           "Logistics", "للخدمات اللوجستية"),
    Sector("clinic", "Medical clinic", "عيادة طبية",
           (200_000, 450_000), (0.18, 0.28),
           (1.0, 1.0, 1.0, 1.0, 1.0, 0.95, 0.9, 0.95, 1.05, 1.05, 1.05, 1.05),
           "Medical Clinic", "الطبية"),
    Sector("print_ads", "Printing and advertising", "طباعة ودعاية وإعلان",
           (170_000, 350_000), (0.15, 0.25),
           (0.95, 1.0, 1.05, 1.1, 1.0, 0.9, 0.85, 0.9, 1.05, 1.05, 1.05, 1.1),
           "Printing & Advertising", "للطباعة والإعلان"),
)

CITIES: tuple[tuple[str, str], ...] = (
    ("Riyadh", "الرياض"), ("Jeddah", "جدة"), ("Dammam", "الدمام"), ("Makkah", "مكة المكرمة"),
    ("Madinah", "المدينة المنورة"), ("Khobar", "الخبر"), ("Abha", "أبها"), ("Tabuk", "تبوك"),
)

# Name stems for "<stem> <sector suffix>" — invented, not real companies.
NAME_STEMS: tuple[tuple[str, str], ...] = (
    ("Al-Noor", "النور"), ("Al-Waha", "الواحة"), ("Al-Fajr", "الفجر"), ("Sahab", "سحاب"),
    ("Al-Rawabi", "الروابي"), ("Najd Line", "خط نجد"), ("Al-Murjan", "المرجان"), ("Tamr", "تمر"),
    ("Al-Bayan", "البيان"), ("Durrat", "درة"), ("Al-Qimma", "القمة"), ("Watan", "وطن"),
    ("Al-Masar", "المسار"), ("Ruya", "رؤية"), ("Al-Nakheel", "النخيل"), ("Sanad Line", "خط السند"),
)
