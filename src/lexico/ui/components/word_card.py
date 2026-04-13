"""Render a WordEntry as a rich card."""

from __future__ import annotations

import streamlit as st

from lexico.domain.word import WordEntry


def render_word_card(entry: WordEntry) -> None:
    header = f"{entry.language.flag} **{entry.lemma}**"
    if entry.ipa:
        header += f"  ·  `{entry.ipa}`"
    if entry.cefr_level:
        header += f"  ·  {entry.cefr_level.value}"
    st.markdown(header)

    for i, sense in enumerate(entry.senses, start=1):
        pos = sense.part_of_speech.value if sense.part_of_speech else ""
        line = f"**{i}.** *{pos}* — {sense.gloss}"
        if sense.register_label:
            line += f"  _({sense.register_label})_"
        st.markdown(line)
        for ex in sense.examples:
            ex_line = f"> _{ex.text}_"
            if ex.translation:
                ex_line += f"  \n> → {ex.translation}"
            st.markdown(ex_line)
        if sense.synonyms:
            st.caption(f"Synonyms: {', '.join(sense.synonyms)}")

    if entry.translations:
        cols = st.columns(len(entry.translations))
        for col, (lang, words) in zip(cols, entry.translations.items()):
            with col:
                st.markdown(f"{lang.flag} **{lang.display_name}**")
                st.write(", ".join(words))

    if entry.etymology:
        with st.expander("Etymology"):
            st.write(entry.etymology)
