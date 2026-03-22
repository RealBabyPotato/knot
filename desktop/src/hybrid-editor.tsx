import { useEffect, useRef, useState } from "react";
import { MarkdownLine } from "./markdown";

type HybridMarkdownEditorProps = {
  value: string;
  onChange: (nextValue: string) => void;
  placeholder?: string;
};

function splitLines(value: string): string[] {
  const parts = value.split("\n");
  return parts.length > 0 ? parts : [""];
}

function replaceActiveLine(lines: string[], index: number, nextLine: string): string[] {
  return lines.map((line, lineIndex) => (lineIndex === index ? nextLine : line));
}

export function HybridMarkdownEditor({
  value,
  onChange,
  placeholder = "# Start writing...",
}: HybridMarkdownEditorProps) {
  const [activeLine, setActiveLine] = useState(0);
  const [preferredColumn, setPreferredColumn] = useState(0);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const lines = splitLines(value);

  useEffect(() => {
    if (activeLine > lines.length - 1) {
      setActiveLine(Math.max(0, lines.length - 1));
    }
  }, [activeLine, lines.length]);

  useEffect(() => {
    const input = inputRef.current;
    if (!focused || !input) {
      return;
    }

    input.style.height = "0px";
    input.style.height = `${Math.max(44, input.scrollHeight)}px`;
    input.focus();

    const offset = Math.min(preferredColumn, lines[activeLine]?.length ?? 0);
    input.setSelectionRange(offset, offset);
  }, [activeLine, focused, lines, preferredColumn]);

  function updateValue(nextLines: string[], nextActiveLine = activeLine, nextColumn = preferredColumn) {
    onChange(nextLines.join("\n"));
    setActiveLine(nextActiveLine);
    setPreferredColumn(nextColumn);
  }

  function focusLine(index: number, column = lines[index]?.length ?? 0) {
    setActiveLine(index);
    setPreferredColumn(column);
    setFocused(true);
  }

  function insertText(text: string, selectionStart: number, selectionEnd: number) {
    const currentLine = lines[activeLine] ?? "";
    const before = currentLine.slice(0, selectionStart);
    const after = currentLine.slice(selectionEnd);
    const nextParts = text.replace(/\r\n/g, "\n").split("\n");

    if (nextParts.length === 1) {
      updateValue(
        replaceActiveLine(lines, activeLine, `${before}${text}${after}`),
        activeLine,
        before.length + text.length,
      );
      return;
    }

    const inserted = [...lines];
    inserted.splice(
      activeLine,
      1,
      `${before}${nextParts[0]}`,
      ...nextParts.slice(1, -1),
      `${nextParts[nextParts.length - 1]}${after}`,
    );
    updateValue(inserted, activeLine + nextParts.length - 1, nextParts[nextParts.length - 1].length);
  }

  return (
    <div className="hybrid-editor">
      {lines.map((line, index) => {
        const isActive = focused && index === activeLine;

        return (
          <div key={`${index}-${line}`} className={isActive ? "hybrid-line active" : "hybrid-line"}>
            <div className="hybrid-line-body">
              {isActive ? (
                <textarea
                  ref={inputRef}
                  rows={1}
                  className="hybrid-line-input"
                  value={line}
                  spellCheck={false}
                  placeholder={placeholder}
                  onBlur={() => {
                    setFocused(false);
                  }}
                  onSelect={(event) => {
                    setPreferredColumn(event.currentTarget.selectionStart);
                  }}
                  onChange={(event) => {
                    updateValue(
                      replaceActiveLine(lines, activeLine, event.target.value),
                      activeLine,
                      event.target.selectionStart,
                    );
                  }}
                  onPaste={(event) => {
                    event.preventDefault();
                    insertText(
                      event.clipboardData.getData("text/plain"),
                      event.currentTarget.selectionStart,
                      event.currentTarget.selectionEnd,
                    );
                  }}
                  onKeyDown={(event) => {
                    const { selectionStart, selectionEnd, value: currentLine } = event.currentTarget;

                    if (event.key === "Enter") {
                      event.preventDefault();
                      const before = currentLine.slice(0, selectionStart);
                      const after = currentLine.slice(selectionEnd);
                      const nextLines = [...lines];
                      nextLines.splice(activeLine, 1, before, after);
                      updateValue(nextLines, activeLine + 1, 0);
                      return;
                    }

                    if (event.key === "Tab") {
                      event.preventDefault();
                      insertText("  ", selectionStart, selectionEnd);
                      return;
                    }

                    if (event.key === "ArrowUp") {
                      event.preventDefault();
                      focusLine(Math.max(0, activeLine - 1), selectionStart);
                      return;
                    }

                    if (event.key === "ArrowDown") {
                      event.preventDefault();
                      focusLine(Math.min(lines.length - 1, activeLine + 1), selectionStart);
                      return;
                    }

                    if (event.key === "Backspace" && selectionStart === selectionEnd && selectionStart === 0 && activeLine > 0) {
                      event.preventDefault();
                      const previous = lines[activeLine - 1] ?? "";
                      const nextLines = [...lines];
                      nextLines.splice(activeLine - 1, 2, `${previous}${currentLine}`);
                      updateValue(nextLines, activeLine - 1, previous.length);
                      return;
                    }

                    if (
                      event.key === "Delete" &&
                      selectionStart === selectionEnd &&
                      selectionStart === currentLine.length &&
                      activeLine < lines.length - 1
                    ) {
                      event.preventDefault();
                      const following = lines[activeLine + 1] ?? "";
                      const nextLines = [...lines];
                      nextLines.splice(activeLine, 2, `${currentLine}${following}`);
                      updateValue(nextLines, activeLine, currentLine.length);
                    }
                  }}
                />
              ) : (
                <button
                  type="button"
                  className="hybrid-line-preview"
                  onClick={() => {
                    focusLine(index);
                  }}
                >
                  <MarkdownLine markdown={line} placeholder={index === 0 ? placeholder : "Continue writing..."} />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
