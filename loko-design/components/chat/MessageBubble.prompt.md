MessageBubble — a single chat message, bot (left, sunken surface) or user (right, brand green).

```jsx
<MessageBubble from="bot" traceLabel="cgv-2026.pdf · state.confirm_return">
  Je peux traiter votre retour si la commande a moins de 30 jours.
</MessageBubble>
```

The `traceLabel` is what makes LOKO's determinism visible in the widget itself — always show it on bot answers that cite a source or state.
