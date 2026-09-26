# Solution architect

You design one change or one system, and bring it into the enterprise model.

## What the repository needs from you

- **The context first:** why the change is made, and which business it changes.
  Name them in the proposal, or answer the assistant's questions about them.
- **The system at the level others meet it:** the application, the interfaces
  other systems call, the data it shares with them, the platform it runs on.
- **Every element traced upward:** each application, data object and technology
  element relates, directly or through others, to the business or strategy it
  serves.

## What stays with your design

The inside of your system — its internal components, internal tables, classes,
deployment detail nothing else uses — stays in your design documents. Link that
page from the system instead. When a new element relates only to its own system,
the assistant offers *Link it from the system*; if something outside the system
does use it, keep it and say what.

## How you work

1. **Hand in the design.** Start from a template on the Propose page, or hand in
   your own document; the assistant reads either.
2. **Answer the questions.** Pick a choice, answer in words, or edit a row. The
   draft is kept between sittings, so a question you cannot answer today waits.
3. **Read what it touches** before you apply: what depends on what you change or
   retire, and who must review it.
4. **Apply to a branch, and ask for review.**

## Drawing a change

You can hand in a drawing instead of a document: a draw.io file read against the
model as it is now.

1. **Start from what the application gives you.** Export a view of the part you
   change, or open the metamodel's shape library (from the Metamodel page) in
   draw.io: one shape per type an element may be. Copy shapes freely.
2. **Say what each new shape is.** A shape from the library, or copied from an
   export, keeps its type. Any other shape takes the type written at the front of
   its label, as `«Type Name» Name`, which also overrides the type a copied shape
   carries; without one, its shape decides where only one type is drawn that
   way. A line drawn between two elements is a new relationship.
3. **Answer what the drawing cannot say.** A shape nothing types is asked about,
   with the likely types first. So are a label edited on an exported shape (a
   rename, or only the drawing's label), a shape or line taken out (out of the
   model, or only out of the picture) and a text box (a note, unless you say it
   is an element). Moving or resizing a shape changes nothing.
4. **Hand the file in on Propose.** Its rows join the conversation as any
   document's do, and nothing is applied until you tick it.
