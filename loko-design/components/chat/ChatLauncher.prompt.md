ChatLauncher — the floating round button that opens/closes the LOKO widget, glyph-derived.

```jsx
<ChatLauncher open={isOpen} onClick={() => setIsOpen(!isOpen)} unread={2} />
```

Variants: closed (shows keyhole glyph), open (shows ×). `unread` renders a small bronze badge — never red, unread isn't an alert.
