"""Render a WordEntry as a rich card."""

from __future__ import annotations

import html

import streamlit as st

from lexico.domain.word import WordEntry


def render_word_card(entry: WordEntry) -> None:
    header = f"{entry.language.flag} **{entry.lemma}**"
    if entry.ipa:
        header += f"  ·  `/{entry.ipa}/`"
    st.markdown(header)

    for i, sense in enumerate(entry.senses, start=1):
        pos = sense.part_of_speech.value if sense.part_of_speech else ""
        line = f"**{i}.** *{pos}* — {sense.gloss}"
        if sense.register_label:
            line += f"  _({sense.register_label})_"
        st.markdown(line)
        for ex in sense.examples:
            # Grey quoted example, with optional translation underneath.
            st.markdown(
                f"<div style='color:#888; margin:2px 0 4px 14px; "
                f"font-size:0.92em;'>&mdash; <em>{html.escape(ex.text)}</em></div>",
                unsafe_allow_html=True,
            )
            if ex.translation:
                st.markdown(
                    f"<div style='color:#888; margin:0 0 4px 14px; "
                    f"font-size:0.92em;'>&nbsp;&nbsp;&rarr; "
                    f"{html.escape(ex.translation)}</div>",
                    unsafe_allow_html=True,
                )
        if sense.synonyms:
            st.caption(f"Synonyms: {', '.join(sense.synonyms)}")

    if entry.derived:
        st.markdown("**Derived forms**")
        st.caption(", ".join(entry.derived))

    if entry.translations:
        cols = st.columns(len(entry.translations))
        for col, (lang, words) in zip(cols, entry.translations.items()):
            with col:
                st.markdown(f"{lang.flag} **{lang.display_name}**")
                st.write(", ".join(words))

    if entry.etymology:
        with st.expander("Etymology"):
            st.write(entry.etymology)
