"""Internationalization utilities for Tamil/English support"""
import json
import os

def load_translations(lang='ta'):
    """Load translation dictionary for given language"""
    try:
        i18n_path = os.path.join('static', 'i18n', f'{lang}.json')
        if os.path.exists(i18n_path):
            with open(i18n_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading translations: {e}")
    return {}

def get_language():
    """Get current language from session, default to Tamil"""
    return session.get('language', 'ta')

def set_language(lang):
    """Set language in session"""
    if lang in ['ta', 'en']:
        session['language'] = lang

def translate(key, lang=None):
    """Translate a key to current language"""
    if lang is None:
        lang = get_language()
    translations = load_translations(lang)
    return translations.get(key, key)

