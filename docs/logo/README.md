# PrinterService logo

The mark tells the story of the project in one glance: a **phone** (magenta) is fed
into the printer's paper-input slot, and the printer outputs a page carrying a
**Wi-Fi symbol** (cyan) — *mobile → printing → wireless*.

Palette is CMYK-inspired:

| Color     | Hex       | Role                          |
| --------- | --------- | ----------------------------- |
| Cyan      | `#00AEEF` | Wi-Fi symbol, status LED      |
| Magenta   | `#E6007E` | phone, "Service" wordmark     |
| Yellow    | `#FFD84D` | printed page                  |
| Dark      | `#24272E` | printer body, "Printer"       |
| White     | `#FFFFFF` | slot openings, phone screen   |

The background is transparent; the body color is lifted slightly so the silhouette
also reads on dark backgrounds.

## Files

| File                            | Use                                              |
| ------------------------------- | ------------------------------------------------ |
| `printerservice-icon.svg`       | Symbol only — favicons, app icons, inline badges |
| `printerservice-logo.svg`       | Horizontal lockup for **light** backgrounds      |
| `printerservice-logo-dark-bg.svg` | Horizontal lockup for **dark** backgrounds     |

## Usage

Icon only:

```markdown
![PrinterService](docs/logo/printerservice-icon.svg)
```

Lockup that adapts to GitHub light/dark theme:

```html
<picture>
  <source media="(prefers-color-scheme: dark)"
          srcset="docs/logo/printerservice-logo-dark-bg.svg">
  <img src="docs/logo/printerservice-logo.svg" alt="PrinterService" width="400">
</picture>
```

## Editing

- All colors are inline `fill` attributes — change them per element; groups are
  named (`#phone`, `#wifi`, `#page`, `#body`, …).
- The mark is duplicated between the three files (no external references), so
  apply any shape change to all of them.
- The wordmark is a real `<text>` element using a system font stack
  (`Segoe UI` / system sans). It stays trivially editable; convert to outlines
  first if you need pixel-identical rendering everywhere.
