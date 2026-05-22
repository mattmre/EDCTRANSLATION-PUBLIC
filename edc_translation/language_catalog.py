"""Language catalog for UI/API selection without constraining engine support."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LanguageOption:
    code: str
    name: str
    code_family: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


AUTO_LANGUAGE_OPTION = LanguageOption("auto", "Auto Detect", "runtime")

COMMON_LANGUAGE_OPTIONS = [
    LanguageOption("af", "Afrikaans", "common"),
    LanguageOption("ak", "Akan", "common"),
    LanguageOption("sq", "Albanian", "common"),
    LanguageOption("am", "Amharic", "common"),
    LanguageOption("ar", "Arabic", "common"),
    LanguageOption("hy", "Armenian", "common"),
    LanguageOption("as", "Assamese", "common"),
    LanguageOption("ay", "Aymara", "common"),
    LanguageOption("az", "Azerbaijani", "common"),
    LanguageOption("bm", "Bambara", "common"),
    LanguageOption("eu", "Basque", "common"),
    LanguageOption("be", "Belarusian", "common"),
    LanguageOption("bn", "Bengali", "common"),
    LanguageOption("bho", "Bhojpuri", "common"),
    LanguageOption("bs", "Bosnian", "common"),
    LanguageOption("bg", "Bulgarian", "common"),
    LanguageOption("my", "Burmese", "common"),
    LanguageOption("ca", "Catalan", "common"),
    LanguageOption("ceb", "Cebuano", "common"),
    LanguageOption("zh", "Chinese", "common"),
    LanguageOption("zh-Hans", "Chinese Simplified", "common"),
    LanguageOption("zh-Hant", "Chinese Traditional", "common"),
    LanguageOption("co", "Corsican", "common"),
    LanguageOption("hr", "Croatian", "common"),
    LanguageOption("cs", "Czech", "common"),
    LanguageOption("da", "Danish", "common"),
    LanguageOption("dv", "Divehi", "common"),
    LanguageOption("doi", "Dogri", "common"),
    LanguageOption("nl", "Dutch", "common"),
    LanguageOption("en", "English", "common"),
    LanguageOption("eo", "Esperanto", "common"),
    LanguageOption("et", "Estonian", "common"),
    LanguageOption("ee", "Ewe", "common"),
    LanguageOption("fil", "Filipino", "common"),
    LanguageOption("fi", "Finnish", "common"),
    LanguageOption("fr", "French", "common"),
    LanguageOption("fy", "Frisian", "common"),
    LanguageOption("gl", "Galician", "common"),
    LanguageOption("lg", "Ganda", "common"),
    LanguageOption("ka", "Georgian", "common"),
    LanguageOption("de", "German", "common"),
    LanguageOption("el", "Greek", "common"),
    LanguageOption("gn", "Guarani", "common"),
    LanguageOption("gu", "Gujarati", "common"),
    LanguageOption("ht", "Haitian Creole", "common"),
    LanguageOption("ha", "Hausa", "common"),
    LanguageOption("haw", "Hawaiian", "common"),
    LanguageOption("he", "Hebrew", "common"),
    LanguageOption("hi", "Hindi", "common"),
    LanguageOption("hmn", "Hmong", "common"),
    LanguageOption("hu", "Hungarian", "common"),
    LanguageOption("is", "Icelandic", "common"),
    LanguageOption("ig", "Igbo", "common"),
    LanguageOption("ilo", "Ilocano", "common"),
    LanguageOption("id", "Indonesian", "common"),
    LanguageOption("ga", "Irish", "common"),
    LanguageOption("it", "Italian", "common"),
    LanguageOption("ja", "Japanese", "common"),
    LanguageOption("jv", "Javanese", "common"),
    LanguageOption("kn", "Kannada", "common"),
    LanguageOption("kk", "Kazakh", "common"),
    LanguageOption("km", "Khmer", "common"),
    LanguageOption("rw", "Kinyarwanda", "common"),
    LanguageOption("gom", "Konkani", "common"),
    LanguageOption("ko", "Korean", "common"),
    LanguageOption("kri", "Krio", "common"),
    LanguageOption("ku", "Kurdish", "common"),
    LanguageOption("ckb", "Kurdish Sorani", "common"),
    LanguageOption("ky", "Kyrgyz", "common"),
    LanguageOption("lo", "Lao", "common"),
    LanguageOption("la", "Latin", "common"),
    LanguageOption("lv", "Latvian", "common"),
    LanguageOption("ln", "Lingala", "common"),
    LanguageOption("lt", "Lithuanian", "common"),
    LanguageOption("lb", "Luxembourgish", "common"),
    LanguageOption("mk", "Macedonian", "common"),
    LanguageOption("mai", "Maithili", "common"),
    LanguageOption("mg", "Malagasy", "common"),
    LanguageOption("ms", "Malay", "common"),
    LanguageOption("ml", "Malayalam", "common"),
    LanguageOption("mt", "Maltese", "common"),
    LanguageOption("mi", "Maori", "common"),
    LanguageOption("mr", "Marathi", "common"),
    LanguageOption("mni", "Meiteilon", "common"),
    LanguageOption("lus", "Mizo", "common"),
    LanguageOption("mn", "Mongolian", "common"),
    LanguageOption("ne", "Nepali", "common"),
    LanguageOption("no", "Norwegian", "common"),
    LanguageOption("ny", "Nyanja", "common"),
    LanguageOption("or", "Odia", "common"),
    LanguageOption("om", "Oromo", "common"),
    LanguageOption("ps", "Pashto", "common"),
    LanguageOption("fa", "Persian", "common"),
    LanguageOption("pl", "Polish", "common"),
    LanguageOption("pt", "Portuguese", "common"),
    LanguageOption("pa", "Punjabi", "common"),
    LanguageOption("qu", "Quechua", "common"),
    LanguageOption("ro", "Romanian", "common"),
    LanguageOption("ru", "Russian", "common"),
    LanguageOption("sm", "Samoan", "common"),
    LanguageOption("sa", "Sanskrit", "common"),
    LanguageOption("gd", "Scottish Gaelic", "common"),
    LanguageOption("nso", "Sepedi", "common"),
    LanguageOption("sr", "Serbian", "common"),
    LanguageOption("st", "Sesotho", "common"),
    LanguageOption("sn", "Shona", "common"),
    LanguageOption("sd", "Sindhi", "common"),
    LanguageOption("si", "Sinhala", "common"),
    LanguageOption("sk", "Slovak", "common"),
    LanguageOption("sl", "Slovenian", "common"),
    LanguageOption("so", "Somali", "common"),
    LanguageOption("es", "Spanish", "common"),
    LanguageOption("su", "Sundanese", "common"),
    LanguageOption("sw", "Swahili", "common"),
    LanguageOption("sv", "Swedish", "common"),
    LanguageOption("tg", "Tajik", "common"),
    LanguageOption("ta", "Tamil", "common"),
    LanguageOption("tt", "Tatar", "common"),
    LanguageOption("te", "Telugu", "common"),
    LanguageOption("th", "Thai", "common"),
    LanguageOption("ti", "Tigrinya", "common"),
    LanguageOption("ts", "Tsonga", "common"),
    LanguageOption("tr", "Turkish", "common"),
    LanguageOption("tk", "Turkmen", "common"),
    LanguageOption("uk", "Ukrainian", "common"),
    LanguageOption("ur", "Urdu", "common"),
    LanguageOption("ug", "Uyghur", "common"),
    LanguageOption("uz", "Uzbek", "common"),
    LanguageOption("vi", "Vietnamese", "common"),
    LanguageOption("cy", "Welsh", "common"),
    LanguageOption("xh", "Xhosa", "common"),
    LanguageOption("yi", "Yiddish", "common"),
    LanguageOption("yo", "Yoruba", "common"),
    LanguageOption("zu", "Zulu", "common"),
]

FLORES_200_LANGUAGE_OPTIONS = [
    LanguageOption("ace_Arab", "Acehnese (Arabic script)", "FLORES/NLLB"),
    LanguageOption("ace_Latn", "Acehnese (Latin script)", "FLORES/NLLB"),
    LanguageOption("acm_Arab", "Mesopotamian Arabic", "FLORES/NLLB"),
    LanguageOption("acq_Arab", "Taizzi-Adeni Arabic", "FLORES/NLLB"),
    LanguageOption("aeb_Arab", "Tunisian Arabic", "FLORES/NLLB"),
    LanguageOption("afr_Latn", "Afrikaans", "FLORES/NLLB"),
    LanguageOption("ajp_Arab", "South Levantine Arabic", "FLORES/NLLB"),
    LanguageOption("aka_Latn", "Akan", "FLORES/NLLB"),
    LanguageOption("amh_Ethi", "Amharic", "FLORES/NLLB"),
    LanguageOption("apc_Arab", "North Levantine Arabic", "FLORES/NLLB"),
    LanguageOption("arb_Arab", "Modern Standard Arabic", "FLORES/NLLB"),
    LanguageOption("arb_Latn", "Modern Standard Arabic (Romanized)", "FLORES/NLLB"),
    LanguageOption("ars_Arab", "Najdi Arabic", "FLORES/NLLB"),
    LanguageOption("ary_Arab", "Moroccan Arabic", "FLORES/NLLB"),
    LanguageOption("arz_Arab", "Egyptian Arabic", "FLORES/NLLB"),
    LanguageOption("asm_Beng", "Assamese", "FLORES/NLLB"),
    LanguageOption("ast_Latn", "Asturian", "FLORES/NLLB"),
    LanguageOption("awa_Deva", "Awadhi", "FLORES/NLLB"),
    LanguageOption("ayr_Latn", "Central Aymara", "FLORES/NLLB"),
    LanguageOption("azb_Arab", "South Azerbaijani", "FLORES/NLLB"),
    LanguageOption("azj_Latn", "North Azerbaijani", "FLORES/NLLB"),
    LanguageOption("bak_Cyrl", "Bashkir", "FLORES/NLLB"),
    LanguageOption("bam_Latn", "Bambara", "FLORES/NLLB"),
    LanguageOption("ban_Latn", "Balinese", "FLORES/NLLB"),
    LanguageOption("bel_Cyrl", "Belarusian", "FLORES/NLLB"),
    LanguageOption("bem_Latn", "Bemba", "FLORES/NLLB"),
    LanguageOption("ben_Beng", "Bengali", "FLORES/NLLB"),
    LanguageOption("bho_Deva", "Bhojpuri", "FLORES/NLLB"),
    LanguageOption("bjn_Arab", "Banjar (Arabic script)", "FLORES/NLLB"),
    LanguageOption("bjn_Latn", "Banjar (Latin script)", "FLORES/NLLB"),
    LanguageOption("bod_Tibt", "Standard Tibetan", "FLORES/NLLB"),
    LanguageOption("bos_Latn", "Bosnian", "FLORES/NLLB"),
    LanguageOption("bug_Latn", "Buginese", "FLORES/NLLB"),
    LanguageOption("bul_Cyrl", "Bulgarian", "FLORES/NLLB"),
    LanguageOption("cat_Latn", "Catalan", "FLORES/NLLB"),
    LanguageOption("ceb_Latn", "Cebuano", "FLORES/NLLB"),
    LanguageOption("ces_Latn", "Czech", "FLORES/NLLB"),
    LanguageOption("cjk_Latn", "Chokwe", "FLORES/NLLB"),
    LanguageOption("ckb_Arab", "Central Kurdish", "FLORES/NLLB"),
    LanguageOption("crh_Latn", "Crimean Tatar", "FLORES/NLLB"),
    LanguageOption("cym_Latn", "Welsh", "FLORES/NLLB"),
    LanguageOption("dan_Latn", "Danish", "FLORES/NLLB"),
    LanguageOption("deu_Latn", "German", "FLORES/NLLB"),
    LanguageOption("dik_Latn", "Southwestern Dinka", "FLORES/NLLB"),
    LanguageOption("dyu_Latn", "Dyula", "FLORES/NLLB"),
    LanguageOption("dzo_Tibt", "Dzongkha", "FLORES/NLLB"),
    LanguageOption("ell_Grek", "Greek", "FLORES/NLLB"),
    LanguageOption("eng_Latn", "English", "FLORES/NLLB"),
    LanguageOption("epo_Latn", "Esperanto", "FLORES/NLLB"),
    LanguageOption("est_Latn", "Estonian", "FLORES/NLLB"),
    LanguageOption("eus_Latn", "Basque", "FLORES/NLLB"),
    LanguageOption("ewe_Latn", "Ewe", "FLORES/NLLB"),
    LanguageOption("fao_Latn", "Faroese", "FLORES/NLLB"),
    LanguageOption("fij_Latn", "Fijian", "FLORES/NLLB"),
    LanguageOption("fin_Latn", "Finnish", "FLORES/NLLB"),
    LanguageOption("fon_Latn", "Fon", "FLORES/NLLB"),
    LanguageOption("fra_Latn", "French", "FLORES/NLLB"),
    LanguageOption("fur_Latn", "Friulian", "FLORES/NLLB"),
    LanguageOption("fuv_Latn", "Nigerian Fulfulde", "FLORES/NLLB"),
    LanguageOption("gla_Latn", "Scottish Gaelic", "FLORES/NLLB"),
    LanguageOption("gle_Latn", "Irish", "FLORES/NLLB"),
    LanguageOption("glg_Latn", "Galician", "FLORES/NLLB"),
    LanguageOption("grn_Latn", "Guarani", "FLORES/NLLB"),
    LanguageOption("guj_Gujr", "Gujarati", "FLORES/NLLB"),
    LanguageOption("hat_Latn", "Haitian Creole", "FLORES/NLLB"),
    LanguageOption("hau_Latn", "Hausa", "FLORES/NLLB"),
    LanguageOption("heb_Hebr", "Hebrew", "FLORES/NLLB"),
    LanguageOption("hin_Deva", "Hindi", "FLORES/NLLB"),
    LanguageOption("hne_Deva", "Chhattisgarhi", "FLORES/NLLB"),
    LanguageOption("hrv_Latn", "Croatian", "FLORES/NLLB"),
    LanguageOption("hun_Latn", "Hungarian", "FLORES/NLLB"),
    LanguageOption("hye_Armn", "Armenian", "FLORES/NLLB"),
    LanguageOption("ibo_Latn", "Igbo", "FLORES/NLLB"),
    LanguageOption("ilo_Latn", "Ilocano", "FLORES/NLLB"),
    LanguageOption("ind_Latn", "Indonesian", "FLORES/NLLB"),
    LanguageOption("isl_Latn", "Icelandic", "FLORES/NLLB"),
    LanguageOption("ita_Latn", "Italian", "FLORES/NLLB"),
    LanguageOption("jav_Latn", "Javanese", "FLORES/NLLB"),
    LanguageOption("jpn_Jpan", "Japanese", "FLORES/NLLB"),
    LanguageOption("kab_Latn", "Kabyle", "FLORES/NLLB"),
    LanguageOption("kac_Latn", "Jingpho", "FLORES/NLLB"),
    LanguageOption("kam_Latn", "Kamba", "FLORES/NLLB"),
    LanguageOption("kan_Knda", "Kannada", "FLORES/NLLB"),
    LanguageOption("kas_Arab", "Kashmiri (Arabic script)", "FLORES/NLLB"),
    LanguageOption("kas_Deva", "Kashmiri (Devanagari script)", "FLORES/NLLB"),
    LanguageOption("kat_Geor", "Georgian", "FLORES/NLLB"),
    LanguageOption("knc_Arab", "Central Kanuri (Arabic script)", "FLORES/NLLB"),
    LanguageOption("knc_Latn", "Central Kanuri (Latin script)", "FLORES/NLLB"),
    LanguageOption("kaz_Cyrl", "Kazakh", "FLORES/NLLB"),
    LanguageOption("kbp_Latn", "Kabiye", "FLORES/NLLB"),
    LanguageOption("kea_Latn", "Kabuverdianu", "FLORES/NLLB"),
    LanguageOption("khm_Khmr", "Khmer", "FLORES/NLLB"),
    LanguageOption("kik_Latn", "Kikuyu", "FLORES/NLLB"),
    LanguageOption("kin_Latn", "Kinyarwanda", "FLORES/NLLB"),
    LanguageOption("kir_Cyrl", "Kyrgyz", "FLORES/NLLB"),
    LanguageOption("kmb_Latn", "Kimbundu", "FLORES/NLLB"),
    LanguageOption("kmr_Latn", "Northern Kurdish", "FLORES/NLLB"),
    LanguageOption("kon_Latn", "Kikongo", "FLORES/NLLB"),
    LanguageOption("kor_Hang", "Korean", "FLORES/NLLB"),
    LanguageOption("lao_Laoo", "Lao", "FLORES/NLLB"),
    LanguageOption("lij_Latn", "Ligurian", "FLORES/NLLB"),
    LanguageOption("lim_Latn", "Limburgish", "FLORES/NLLB"),
    LanguageOption("lin_Latn", "Lingala", "FLORES/NLLB"),
    LanguageOption("lit_Latn", "Lithuanian", "FLORES/NLLB"),
    LanguageOption("lmo_Latn", "Lombard", "FLORES/NLLB"),
    LanguageOption("ltg_Latn", "Latgalian", "FLORES/NLLB"),
    LanguageOption("ltz_Latn", "Luxembourgish", "FLORES/NLLB"),
    LanguageOption("lua_Latn", "Luba-Kasai", "FLORES/NLLB"),
    LanguageOption("lug_Latn", "Ganda", "FLORES/NLLB"),
    LanguageOption("luo_Latn", "Luo", "FLORES/NLLB"),
    LanguageOption("lus_Latn", "Mizo", "FLORES/NLLB"),
    LanguageOption("lvs_Latn", "Standard Latvian", "FLORES/NLLB"),
    LanguageOption("mag_Deva", "Magahi", "FLORES/NLLB"),
    LanguageOption("mai_Deva", "Maithili", "FLORES/NLLB"),
    LanguageOption("mal_Mlym", "Malayalam", "FLORES/NLLB"),
    LanguageOption("mar_Deva", "Marathi", "FLORES/NLLB"),
    LanguageOption("min_Arab", "Minangkabau (Arabic script)", "FLORES/NLLB"),
    LanguageOption("min_Latn", "Minangkabau (Latin script)", "FLORES/NLLB"),
    LanguageOption("mkd_Cyrl", "Macedonian", "FLORES/NLLB"),
    LanguageOption("plt_Latn", "Plateau Malagasy", "FLORES/NLLB"),
    LanguageOption("mlt_Latn", "Maltese", "FLORES/NLLB"),
    LanguageOption("mni_Beng", "Meitei (Bengali script)", "FLORES/NLLB"),
    LanguageOption("khk_Cyrl", "Halh Mongolian", "FLORES/NLLB"),
    LanguageOption("mos_Latn", "Mossi", "FLORES/NLLB"),
    LanguageOption("mri_Latn", "Maori", "FLORES/NLLB"),
    LanguageOption("mya_Mymr", "Burmese", "FLORES/NLLB"),
    LanguageOption("nld_Latn", "Dutch", "FLORES/NLLB"),
    LanguageOption("nno_Latn", "Norwegian Nynorsk", "FLORES/NLLB"),
    LanguageOption("nob_Latn", "Norwegian Bokmal", "FLORES/NLLB"),
    LanguageOption("npi_Deva", "Nepali", "FLORES/NLLB"),
    LanguageOption("nso_Latn", "Northern Sotho", "FLORES/NLLB"),
    LanguageOption("nus_Latn", "Nuer", "FLORES/NLLB"),
    LanguageOption("nya_Latn", "Nyanja", "FLORES/NLLB"),
    LanguageOption("oci_Latn", "Occitan", "FLORES/NLLB"),
    LanguageOption("gaz_Latn", "West Central Oromo", "FLORES/NLLB"),
    LanguageOption("ory_Orya", "Odia", "FLORES/NLLB"),
    LanguageOption("pag_Latn", "Pangasinan", "FLORES/NLLB"),
    LanguageOption("pan_Guru", "Eastern Panjabi", "FLORES/NLLB"),
    LanguageOption("pap_Latn", "Papiamento", "FLORES/NLLB"),
    LanguageOption("pes_Arab", "Western Persian", "FLORES/NLLB"),
    LanguageOption("pol_Latn", "Polish", "FLORES/NLLB"),
    LanguageOption("por_Latn", "Portuguese", "FLORES/NLLB"),
    LanguageOption("prs_Arab", "Dari", "FLORES/NLLB"),
    LanguageOption("pbt_Arab", "Southern Pashto", "FLORES/NLLB"),
    LanguageOption("quy_Latn", "Ayacucho Quechua", "FLORES/NLLB"),
    LanguageOption("ron_Latn", "Romanian", "FLORES/NLLB"),
    LanguageOption("run_Latn", "Rundi", "FLORES/NLLB"),
    LanguageOption("rus_Cyrl", "Russian", "FLORES/NLLB"),
    LanguageOption("sag_Latn", "Sango", "FLORES/NLLB"),
    LanguageOption("san_Deva", "Sanskrit", "FLORES/NLLB"),
    LanguageOption("sat_Olck", "Santali", "FLORES/NLLB"),
    LanguageOption("scn_Latn", "Sicilian", "FLORES/NLLB"),
    LanguageOption("shn_Mymr", "Shan", "FLORES/NLLB"),
    LanguageOption("sin_Sinh", "Sinhala", "FLORES/NLLB"),
    LanguageOption("slk_Latn", "Slovak", "FLORES/NLLB"),
    LanguageOption("slv_Latn", "Slovenian", "FLORES/NLLB"),
    LanguageOption("smo_Latn", "Samoan", "FLORES/NLLB"),
    LanguageOption("sna_Latn", "Shona", "FLORES/NLLB"),
    LanguageOption("snd_Arab", "Sindhi", "FLORES/NLLB"),
    LanguageOption("som_Latn", "Somali", "FLORES/NLLB"),
    LanguageOption("sot_Latn", "Southern Sotho", "FLORES/NLLB"),
    LanguageOption("spa_Latn", "Spanish", "FLORES/NLLB"),
    LanguageOption("als_Latn", "Tosk Albanian", "FLORES/NLLB"),
    LanguageOption("srd_Latn", "Sardinian", "FLORES/NLLB"),
    LanguageOption("srp_Cyrl", "Serbian", "FLORES/NLLB"),
    LanguageOption("ssw_Latn", "Swati", "FLORES/NLLB"),
    LanguageOption("sun_Latn", "Sundanese", "FLORES/NLLB"),
    LanguageOption("swe_Latn", "Swedish", "FLORES/NLLB"),
    LanguageOption("swh_Latn", "Swahili", "FLORES/NLLB"),
    LanguageOption("szl_Latn", "Silesian", "FLORES/NLLB"),
    LanguageOption("tam_Taml", "Tamil", "FLORES/NLLB"),
    LanguageOption("tat_Cyrl", "Tatar", "FLORES/NLLB"),
    LanguageOption("tel_Telu", "Telugu", "FLORES/NLLB"),
    LanguageOption("tgk_Cyrl", "Tajik", "FLORES/NLLB"),
    LanguageOption("tgl_Latn", "Tagalog", "FLORES/NLLB"),
    LanguageOption("tha_Thai", "Thai", "FLORES/NLLB"),
    LanguageOption("tir_Ethi", "Tigrinya", "FLORES/NLLB"),
    LanguageOption("taq_Latn", "Tamasheq (Latin script)", "FLORES/NLLB"),
    LanguageOption("taq_Tfng", "Tamasheq (Tifinagh script)", "FLORES/NLLB"),
    LanguageOption("tpi_Latn", "Tok Pisin", "FLORES/NLLB"),
    LanguageOption("tsn_Latn", "Tswana", "FLORES/NLLB"),
    LanguageOption("tso_Latn", "Tsonga", "FLORES/NLLB"),
    LanguageOption("tuk_Latn", "Turkmen", "FLORES/NLLB"),
    LanguageOption("tum_Latn", "Tumbuka", "FLORES/NLLB"),
    LanguageOption("tur_Latn", "Turkish", "FLORES/NLLB"),
    LanguageOption("twi_Latn", "Twi", "FLORES/NLLB"),
    LanguageOption("tzm_Tfng", "Central Atlas Tamazight", "FLORES/NLLB"),
    LanguageOption("uig_Arab", "Uyghur", "FLORES/NLLB"),
    LanguageOption("ukr_Cyrl", "Ukrainian", "FLORES/NLLB"),
    LanguageOption("umb_Latn", "Umbundu", "FLORES/NLLB"),
    LanguageOption("urd_Arab", "Urdu", "FLORES/NLLB"),
    LanguageOption("uzn_Latn", "Northern Uzbek", "FLORES/NLLB"),
    LanguageOption("vec_Latn", "Venetian", "FLORES/NLLB"),
    LanguageOption("vie_Latn", "Vietnamese", "FLORES/NLLB"),
    LanguageOption("war_Latn", "Waray", "FLORES/NLLB"),
    LanguageOption("wol_Latn", "Wolof", "FLORES/NLLB"),
    LanguageOption("xho_Latn", "Xhosa", "FLORES/NLLB"),
    LanguageOption("ydd_Hebr", "Eastern Yiddish", "FLORES/NLLB"),
    LanguageOption("yor_Latn", "Yoruba", "FLORES/NLLB"),
    LanguageOption("yue_Hant", "Yue Chinese", "FLORES/NLLB"),
    LanguageOption("zho_Hans", "Chinese (Simplified)", "FLORES/NLLB"),
    LanguageOption("zho_Hant", "Chinese (Traditional)", "FLORES/NLLB"),
    LanguageOption("zsm_Latn", "Standard Malay", "FLORES/NLLB"),
    LanguageOption("zul_Latn", "Zulu", "FLORES/NLLB"),
]

PROVIDER_LANGUAGE_CAPABILITIES = {
    "fasttext_lid": {
        "role": "language-identification",
        "language_count": 176,
        "code_family": "ISO 639 style labels",
        "source": "fastText lid.176 language identification model",
    },
    "nllb_200": {
        "role": "translation",
        "language_count": 200,
        "code_family": "FLORES/NLLB codes",
        "source": "Meta NLLB-200",
    },
    "madlad_400": {
        "role": "translation",
        "language_count": 419,
        "code_family": "MADLAD language set",
        "source": "MADLAD-400 dataset/model family",
    },
    "openai_compatible_llm": {
        "role": "translation",
        "language_count": None,
        "code_family": "provider/model dependent",
        "source": "configured local/cloud LLM",
    },
}

LLM_PROVIDER_IDS = {
    "local_openai_compat",
    "openrouter_llm",
    "google_gemini",
}
ANY_CATALOG_PROVIDER_IDS = {
    "auto",
    "deterministic_ci",
    "stub",
    *LLM_PROVIDER_IDS,
}
COMMON_DEFAULT_TARGET = "en"
COMMON_ALTERNATE_TARGET = "fr"
FLORES_DEFAULT_TARGET = "eng_Latn"
FLORES_ALTERNATE_TARGET = "fra_Latn"
OPUS_MODEL_DIR_ENV = "EDC_TRANSLATION_LOCAL_CT2_OPUS_MODEL_DIR"


def list_language_options(*, include_auto: bool = True) -> list[dict[str, Any]]:
    options = [*COMMON_LANGUAGE_OPTIONS, *FLORES_200_LANGUAGE_OPTIONS]
    if include_auto:
        options = [AUTO_LANGUAGE_OPTION, *options]
    seen: set[str] = set()
    unique_options = []
    for option in options:
        if option.code in seen:
            continue
        seen.add(option.code)
        unique_options.append(option.to_dict())
    return unique_options


def provider_language_matrices() -> dict[str, dict[str, Any]]:
    common_codes = [option.code for option in COMMON_LANGUAGE_OPTIONS]
    flores_codes = [option.code for option in FLORES_200_LANGUAGE_OPTIONS]
    all_source_codes = ["auto", *common_codes, *flores_codes]
    all_target_codes = [*common_codes, *flores_codes]

    matrices = {
        "passthrough": {
            "known_matrix": True,
            "matrix_type": "same_language",
            "source_codes": all_target_codes,
            "target_codes": all_target_codes,
            "target_strategy": "same_as_source",
            "default_source": COMMON_DEFAULT_TARGET,
            "default_target": COMMON_DEFAULT_TARGET,
            "reason": "Passthrough only preserves text and should be used for same-language flows.",
        },
        "local_ct2_nllb": {
            "known_matrix": True,
            "matrix_type": "many_to_many",
            "source_codes": ["auto", *flores_codes],
            "target_codes": flores_codes,
            "default_source": "auto",
            "default_target": FLORES_DEFAULT_TARGET,
            "alternate_target": FLORES_ALTERNATE_TARGET,
            "reason": "NLLB-200 is represented as a many-to-many FLORES/NLLB code matrix.",
        },
        "local_ct2_madlad": {
            "known_matrix": False,
            "matrix_type": "provider_family_broad",
            "source_codes": all_source_codes,
            "target_codes": all_target_codes,
            "default_source": "auto",
            "default_target": COMMON_DEFAULT_TARGET,
            "alternate_target": COMMON_ALTERNATE_TARGET,
            "filter_strategy": "source_code_family",
            "reason": (
                "MADLAD-400-family assets are broad, but the converted local model "
                "must publish its exact tokenizer language matrix before the UI can "
                "constrain pairs more tightly."
            ),
        },
    }
    matrices["local_ct2_opus"] = _opus_matrix(all_source_codes, all_target_codes)
    for provider_id in ANY_CATALOG_PROVIDER_IDS:
        matrices[provider_id] = {
            "known_matrix": provider_id in {"deterministic_ci", "stub"},
            "matrix_type": "test_any" if provider_id in {"deterministic_ci", "stub"} else "provider_model_dependent",
            "source_codes": all_source_codes,
            "target_codes": all_target_codes,
            "default_source": "auto",
            "default_target": COMMON_DEFAULT_TARGET,
            "alternate_target": COMMON_ALTERNATE_TARGET,
            "filter_strategy": "source_code_family",
            "reason": (
                "Test provider accepts any catalog pair."
                if provider_id in {"deterministic_ci", "stub"}
                else "Exact language support is provider/model dependent; keep a broad list and let live/provider validation decide."
            ),
        }
    return matrices


def equivalent_language_codes() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for option in [*COMMON_LANGUAGE_OPTIONS, *FLORES_200_LANGUAGE_OPTIONS]:
        groups[_language_name_key(option.name)].append(option.code)
    equivalents: dict[str, list[str]] = {}
    for codes in groups.values():
        if len(codes) < 2:
            continue
        for code in codes:
            equivalents[code] = codes
    return equivalents


def _opus_matrix(
    all_source_codes: list[str],
    all_target_codes: list[str],
) -> dict[str, Any]:
    pairs = _configured_opus_pairs()
    if not pairs:
        return {
            "known_matrix": False,
            "matrix_type": "configured_model_specific",
            "source_codes": all_source_codes,
            "target_codes": all_target_codes,
            "default_source": "auto",
            "default_target": COMMON_DEFAULT_TARGET,
            "alternate_target": COMMON_ALTERNATE_TARGET,
            "filter_strategy": "source_code_family",
            "reason": (
                "OPUS-MT models are language-pair specific. Add supported_pairs, "
                "source_languages/target_languages, or a parseable model directory "
                "name such as opus-en-fr to constrain the matrix."
            ),
        }

    pair_map: dict[str, list[str]] = defaultdict(list)
    for source, target in pairs:
        pair_map[source].append(target)
    source_codes = sorted(pair_map)
    target_codes = sorted({target for targets in pair_map.values() for target in targets})
    return {
        "known_matrix": True,
        "matrix_type": "configured_model_pairs",
        "source_codes": ["auto", *source_codes],
        "target_codes": target_codes,
        "pairs": {source: sorted(set(targets)) for source, targets in pair_map.items()},
        "default_source": "auto",
        "default_target": target_codes[0] if target_codes else COMMON_DEFAULT_TARGET,
        "reason": "OPUS-MT target list is constrained by configured model pair metadata.",
    }


def _configured_opus_pairs() -> list[tuple[str, str]]:
    raw_model_dir = os.getenv(OPUS_MODEL_DIR_ENV, "").strip()
    if not raw_model_dir:
        return []

    path = Path(raw_model_dir)
    pairs = _opus_pairs_from_provenance(path / "provenance.json")
    if pairs:
        return pairs
    return _opus_pairs_from_name(path.name)


def _opus_pairs_from_provenance(path: Path) -> list[tuple[str, str]]:
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []

    supported_pairs = payload.get("supported_pairs")
    if isinstance(supported_pairs, list):
        pairs = []
        for item in supported_pairs:
            if (
                isinstance(item, list | tuple)
                and len(item) == 2
                and all(isinstance(value, str) for value in item)
            ):
                pairs.append((item[0], item[1]))
        if pairs:
            return pairs

    source_languages = payload.get("source_languages")
    target_languages = payload.get("target_languages")
    if isinstance(source_languages, list) and isinstance(target_languages, list):
        sources = [value for value in source_languages if isinstance(value, str)]
        targets = [value for value in target_languages if isinstance(value, str)]
        return [(source, target) for source in sources for target in targets]
    return []


def _opus_pairs_from_name(name: str) -> list[tuple[str, str]]:
    normalized = name.lower()
    normalized = normalized.replace("opus-mt-", "")
    normalized = normalized.replace("opus-", "")
    parts = [part for part in re.split(r"[-_]", normalized) if part]
    if len(parts) < 2:
        return []
    return [(parts[-2], parts[-1])]


def _language_name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def language_catalog_payload() -> dict[str, Any]:
    languages = list_language_options()
    return {
        "languages": languages,
        "language_count": len(languages),
        "free_form_supported": True,
        "note": (
            "The catalog is a UI helper, not a hard provider limit. "
            "Provider routing and configured model bundles decide actual pair support."
        ),
        "catalogs": {
            "common": {
                "language_count": len(COMMON_LANGUAGE_OPTIONS),
                "code_family": "BCP-47/ISO-style tags",
            },
            "flores_200": {
                "language_count": len(FLORES_200_LANGUAGE_OPTIONS),
                "code_family": "FLORES/NLLB script-qualified tags",
            },
        },
        "provider_capabilities": PROVIDER_LANGUAGE_CAPABILITIES,
        "provider_language_matrices": provider_language_matrices(),
        "equivalent_codes": equivalent_language_codes(),
    }
