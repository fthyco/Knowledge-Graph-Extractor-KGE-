# 📚 Study Process Reference

Welcome to the PDF Reader & Organizer! This tool is specifically designed to eliminate the hallucination issues LLMs (like ChatGPT, Claude, and Gemini) have when reading long, math-heavy PDFs. 

By analyzing the structure, extracting formulas, and formatting the $\LaTeX$ deterministically *before* the AI sees it, the generated prompts give the LLM perfect context.

Here is how you should use this tool to optimize your studying.

## 1. Organizing Your Library
Upload your textbooks, papers, or slide decks using the **Upload PDF** button or by placing them into the `raw_source` folder and clicking **Scan Library**. The system will automatically:
- Read the entire PDF.
- Fix broken mathematical structures.
- Split the book into logical chapters based on Table of Contents and headings.

## 2. Choosing a Study Mode
Once you select a chapter, you can generate a prompt based on how you want to interact with the material.

* **Deep Dive:** Forces the AI to break down the hardest concepts step-by-step. Best for your first pass through dense mathematical material.
* **Exam Prep:** Asks the AI to generate practice questions, focusing heavily on the critical formulas extracted by the Engine.
* **Quick Review:** Generates a highly condensed cheat-sheet style summary of the chapter's core concepts.
* **Socratic:** Instructs the AI to act as a harsh but fair tutor, testing your knowledge with leading questions rather than just giving you the answers.

## 3. Interacting with the Prompt
When you click **Generate Study Prompt**, the resulting text is a densely structured instruction set meant for the AI, *not for you to read*. 

**Your workflow:**
1. Click the **Copy Prompt** button.
2. Open your preferred LLM interface (ChatGPT, Claude, etc.).
3. Paste the prompt and press send.
4. Let the AI guide you through the material. Ask follow-up questions if a specific formula derivation is confusing.

## Tips for Success
- **Broken Math?** If the generated prompt seems to have weirdly formatted text, the original PDF might have had a very strange layout. The `latexfix` pipeline usually handles this, but scanned documents (images) rely heavily on OCR quality.
- **Cross-References:** The deep dive prompt automatically searches your other uploaded books for overlapping concepts. If you're struggling, ask the AI to explain the concept using the cross-references provided.

*Happy Studying!*
