// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/chip-tone.js
//
// Colours every <mj-chip data-tone="ok|warn|error|neutral"> wherever it
// is rendered.
//
// The bundles colour status chips with ``.x__badge[data-tone=...]::part(chip)``
// rules. Those only match chips in the page's own tree; a chip a bundle
// hands to <mj-data-table> is rendered inside the table's shadow root,
// where no page stylesheet reaches, so every state in every list was
// the same grey and a failed run looked like a completed one (ORC-09).
//
// mj-chip draws itself from inherited custom properties
// (--mj-chip-bg / --mj-chip-color / --mj-chip-border-color), and custom
// properties do cross shadow boundaries. So when a chip connects (its
// onConnected hook), this sets them inline from its data-tone -- and again whenever data-tone
// changes -- using the shared --pyc-color-* tone tokens (which carry
// their own dark-mode values).

const TONE_PROPERTIES = {
    ok: {
        "--mj-chip-bg": "var(--pyc-color-success-surface, hsla(145, 63%, 42%, 0.16))",
        "--mj-chip-color": "var(--pyc-color-on-success-surface, hsl(145, 63%, 24%))",
        "--mj-chip-border-color": "transparent"
    },
    warn: {
        "--mj-chip-bg": "var(--pyc-color-warning-surface, hsla(38, 100%, 67%, 0.2))",
        "--mj-chip-color": "var(--pyc-color-on-warning-surface, hsl(32, 75%, 21%))",
        "--mj-chip-border-color": "transparent"
    },
    error: {
        "--mj-chip-bg": "var(--pyc-color-error-surface, hsla(0, 72%, 51%, 0.14))",
        "--mj-chip-color": "var(--pyc-color-on-error-surface, hsl(0, 72%, 34%))",
        "--mj-chip-border-color": "transparent"
    }
};
const MANAGED_PROPERTIES = ["--mj-chip-bg", "--mj-chip-color", "--mj-chip-border-color"];
const TONE_ATTRIBUTE = "data-tone";
const PATCHED_FLAG = "__pycChipTonePatched";
const OBSERVER_KEY = "__pycChipToneObserver";

function apply_chip_tone(chip) {
    const tone = chip.getAttribute(TONE_ATTRIBUTE) || "";
    const properties = TONE_PROPERTIES[tone];
    for (const name of MANAGED_PROPERTIES) {
        if (properties !== undefined) {
            chip.style.setProperty(name, properties[name]);
        } else {
            chip.style.removeProperty(name);
        }
    }
    return;
}

function watch_chip_tone(chip) {
    apply_chip_tone(chip);
    if (chip[OBSERVER_KEY] === undefined && typeof MutationObserver === "function") {
        const observer = new MutationObserver(() => { apply_chip_tone(chip); });
        observer.observe(chip, { attributes: true, attributeFilter: [TONE_ATTRIBUTE] });
        chip[OBSERVER_KEY] = observer;
    }
    return;
}

// The browser captures connectedCallback / disconnectedCallback when
// the element is defined, so wrapping those afterwards does nothing.
// MjElement's lifecycle callbacks call the onConnected / onDisconnected
// hooks through an ordinary property lookup, so those are wrapped.
function patch_chip_class(chip_class) {
    const proto = chip_class.prototype;
    if (proto[PATCHED_FLAG] === true) {
        return;
    }
    proto[PATCHED_FLAG] = true;
    const original_connected = proto.onConnected;
    const original_disconnected = proto.onDisconnected;
    proto.onConnected = function onConnected() {
        if (typeof original_connected === "function") {
            original_connected.call(this);
        }
        watch_chip_tone(this);
        return;
    };
    proto.onDisconnected = function onDisconnected() {
        if (typeof original_disconnected === "function") {
            original_disconnected.call(this);
        }
        const observer = this[OBSERVER_KEY];
        if (observer !== undefined) {
            observer.disconnect();
            delete this[OBSERVER_KEY];
        }
        return;
    };
    return;
}

function install_chip_tone() {
    if (typeof customElements === "undefined") {
        return;
    }
    customElements.whenDefined("mj-chip").then(() => {
        patch_chip_class(customElements.get("mj-chip"));
        // Chips that connected before the patch (page-level ones; chips
        // inside shadow roots render later, from fetched data).
        document.querySelectorAll("mj-chip[" + TONE_ATTRIBUTE + "]").forEach((chip) => { watch_chip_tone(chip); });
    });
    return;
}

export {
    TONE_PROPERTIES,
    apply_chip_tone,
    install_chip_tone,
    patch_chip_class
};
