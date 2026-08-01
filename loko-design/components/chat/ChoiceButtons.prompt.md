ChoiceButtons — pill buttons for the bot's closed-set clarifying questions ("qualifie avant de répondre").

```jsx
<ChoiceButtons options={['Livraison', 'Retour', 'Facturation']} onSelect={setAnswer} selected={answer} />
```

Never free-text where a closed set exists — it's core to the deterministic-flow promise, and the UI should visibly reflect that this is a fixed menu, not a suggestion.
