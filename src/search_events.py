"""
Minimal Streamlit Custom Component (CCv2, native to Streamlit 1.64+) that
distinguishes a debounced "change" event from an Enter-key "submit"
event on ONE text input -- exactly the boundary Main Search needs to
keep PartsBox filtering live while typing without ever querying Mouser/
DigiKey until the operator explicitly presses Enter (the architecture
audit's "minimal Enter-event adapter" precondition).

Contains no search, PartsBox/Mouser/DigiKey, BOM, filter, or purchasing
logic -- it exists only to expose {value, submitted} from one input, per
the audit's explicit instruction that the adapter itself stay this thin.
Built with ONLY Custom Components v2 APIs (st.components.v2.component,
setStateValue/setTriggerValue) -- the legacy v1 declare_component/
postMessage/Streamlit.setComponentValue protocol is deliberately not
used anywhere in this file.
"""

import streamlit as st

_HTML = """
<div class="autobom-search-input-wrap">
  <input id="autobom-search-input" type="text" autocomplete="off" />
</div>
"""

# Uses Streamlit's own theme CSS variables (--st-*) so this single input
# adapts to the app's active theme instead of hardcoding colors, per
# CCv2's theming guidance.
_CSS = """
.autobom-search-input-wrap { width: 100%; }
#autobom-search-input {
  width: 100%;
  box-sizing: border-box;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--st-border-color, #d0d7de);
  border-radius: 0.5rem;
  font-size: 1rem;
  font-family: var(--st-font, inherit);
  color: var(--st-text-color, inherit);
  background: var(--st-background-color, #fff);
}
#autobom-search-input:focus {
  outline: none;
  border-color: var(--st-primary-color, #2563eb);
}
"""

# Debounced "change": every keystroke resets a setTimeout; only the
# value after debounce_ms of no further typing is sent to Python as
# state (drives PartsBox live filtering -- cheap/local, safe to fire
# often). Enter clears any pending debounce and immediately sends BOTH
# the state value (so the box's own displayed value/PartsBox filtering
# doesn't lag behind) and a one-shot trigger (drives the Mouser/DigiKey
# query -- see search_event_input()'s docstring for how `.submitted`
# resets to None on every subsequent rerun that isn't itself an Enter
# press, so this never causes a repeated supplier call).
_JS = """
export default function (component) {
  const { data, parentElement, setStateValue, setTriggerValue } = component

  const input = parentElement.querySelector("#autobom-search-input")
  if (!input) return

  const nextValue = (data && data.value) ?? ""
  if (input.value !== nextValue) {
    input.value = nextValue
  }
  if (data && data.placeholder) {
    input.placeholder = data.placeholder
  }

  const debounceMs = (data && data.debounce_ms) || 350

  input.oninput = (e) => {
    const val = e.target.value
    if (parentElement.__autobomDebounceTimer) {
      clearTimeout(parentElement.__autobomDebounceTimer)
    }
    parentElement.__autobomDebounceTimer = setTimeout(() => {
      setStateValue("value", val)
    }, debounceMs)
  }

  input.onkeydown = (e) => {
    if (e.key === "Enter") {
      if (parentElement.__autobomDebounceTimer) {
        clearTimeout(parentElement.__autobomDebounceTimer)
      }
      setStateValue("value", e.target.value)
      setTriggerValue("submitted", e.target.value)
    }
  }
}
"""

_COMPONENT = st.components.v2.component(
    "autobom_search_event_input",
    html=_HTML,
    css=_CSS,
    js=_JS,
)


def search_event_input(*, key, value="", placeholder="", debounce_ms=350):
    """
    Renders the one search box used for both PartsBox live filtering and
    the Mouser/DigiKey Enter-committed query. Returns a result object
    with:

      .value      the latest debounced text -- updates ~debounce_ms
                  after the operator stops typing, or immediately on
                  Enter. Drive PartsBox local filtering from this on
                  every run.
      .submitted  the text as of the most recent Enter press, or None on
                  any run where Enter was not just pressed (a trigger
                  value -- resets to None after the one rerun it fires
                  on). Drive Mouser/DigiKey queries from this, and ONLY
                  when it is not None -- never from `.value`.

    `value` seeds/re-syncs the input's displayed text from Python (e.g.
    a "Clear search" action); pass the current session_state value back
    each run to leave the box alone otherwise (true-sync pattern).
    """
    component_state = st.session_state.get(key, {})
    current_value = component_state.get("value", value)

    return _COMPONENT(
        key=key,
        data={"value": current_value, "placeholder": placeholder, "debounce_ms": debounce_ms},
        # default={"value": ...} makes .value read as "" (not None)
        # before any real browser has run the frontend JS and called
        # setStateValue -- e.g. the very first render of a fresh
        # session. Every default key requires its on_<key>_change
        # callback per CCv2 (see ccv2-state-sync.md); .submitted has no
        # default since it's a one-shot trigger, not a state value.
        default={"value": value},
        on_value_change=lambda: None,
        on_submitted_change=lambda: None,
    )
