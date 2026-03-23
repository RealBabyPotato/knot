import { useEffect, useRef, useState } from "react";
import { MarkdownLine, MarkdownPreview } from "./markdown";
import { cn } from "@/lib/utils";

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

function offsetToLineColumn(value: string, offset: number): { line: number; column: number } {
  const boundedOffset = Math.max(0, Math.min(offset, value.length));
  const lines = splitLines(value);
  let traversed = 0;

  for (let index = 0; index < lines.length; index += 1) {
    const lineLength = (lines[index] ?? "").length;
    const lineEnd = traversed + lineLength;
    if (boundedOffset <= lineEnd) {
      return { line: index, column: boundedOffset - traversed };
    }
    traversed = lineEnd + 1;
  }

  const lastLine = Math.max(0, lines.length - 1);
  return { line: lastLine, column: lines[lastLine]?.length ?? 0 };
}

type RenderBlock =
  | {
      type: "line";
      index: number;
      line: string;
    }
  | {
      type: "details";
      start: number;
      end: number;
      markdown: string;
    };

function findDetailsBlockEnd(lines: string[], start: number): number | null {
  for (let index = start + 1; index < lines.length; index += 1) {
    if (lines[index]?.trim().startsWith("</details")) {
      return index;
    }
  }
  return null;
}

function buildRenderBlocks(lines: string[], activeLine: number, focused: boolean): RenderBlock[] {
  const blocks: RenderBlock[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();

    if (trimmed.startsWith("<details")) {
      const end = findDetailsBlockEnd(lines, index);
      if (end !== null) {
        const activeInside = focused && activeLine >= index && activeLine <= end;
        if (!activeInside) {
          blocks.push({
            type: "details",
            start: index,
            end,
            markdown: lines.slice(index, end + 1).join("\n"),
          });
          index = end;
          continue;
        }
      }
    }

    blocks.push({
      type: "line",
      index,
      line,
    });
  }

  return blocks;
}

function shouldEnterEditMode(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return true;
  }

  return !target.closest("a, button, input, textarea, select, summary");
}

export function HybridMarkdownEditor({
  value,
  onChange,
  placeholder = "# Start writing...",
}: HybridMarkdownEditorProps) {
  const [activeLine, setActiveLine] = useState(0);
  const [preferredColumn, setPreferredColumn] = useState(0);
  const [focused, setFocused] = useState(false);
  const [documentMode, setDocumentMode] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const documentInputRef = useRef<HTMLTextAreaElement | null>(null);
  const lineSelectionRef = useRef({ start: 0, end: 0 });
  const documentSelectionRef = useRef({ start: 0, end: 0 });
  const lines = splitLines(value);
  const isDocumentEmpty = value.trim().length === 0;
  const renderBlocks = buildRenderBlocks(lines, activeLine, focused);
  const activeLineValue = lines[activeLine] ?? "";

  useEffect(() => {
    if (activeLine > lines.length - 1) {
      setActiveLine(Math.max(0, lines.length - 1));
    }
  }, [activeLine, lines.length]);

  useEffect(() => {
    const input = inputRef.current;
    if (!focused || documentMode || !input) {
      return;
    }

    input.style.height = "0px";
    input.style.height = `${Math.max(44, input.scrollHeight)}px`;
    input.focus();

    const start = Math.min(lineSelectionRef.current.start, activeLineValue.length);
    const end = Math.min(lineSelectionRef.current.end, activeLineValue.length);
    input.setSelectionRange(start, end);
  }, [activeLine, activeLineValue, documentMode, focused]);

  useEffect(() => {
    const input = documentInputRef.current;
    if (!documentMode || !input) {
      return;
    }

    input.style.height = "0px";
    input.style.height = `${Math.max(44, input.scrollHeight)}px`;
    input.focus();

    const start = Math.min(documentSelectionRef.current.start, value.length);
    const end = Math.min(documentSelectionRef.current.end, value.length);
    input.setSelectionRange(start, end);
  }, [documentMode, value]);

  function updateValue(nextLines: string[], nextActiveLine = activeLine, nextColumn = preferredColumn) {
    onChange(nextLines.join("\n"));
    setActiveLine(nextActiveLine);
    setPreferredColumn(nextColumn);
  }

  function focusLine(index: number, column = lines[index]?.length ?? 0) {
    lineSelectionRef.current = { start: column, end: column };
    setActiveLine(index);
    setPreferredColumn(column);
    setDocumentMode(false);
    setFocused(true);
  }

  function setLineSelection(start: number, end = start) {
    lineSelectionRef.current = { start, end };
    setPreferredColumn(start);
  }

  function enterDocumentMode(selectionStart: number, selectionEnd: number) {
    documentSelectionRef.current = { start: selectionStart, end: selectionEnd };
    setDocumentMode(true);
    setFocused(true);
  }

  function syncCursorFromDocument(nextValue: string, selectionStart: number) {
    const cursor = offsetToLineColumn(nextValue, selectionStart);
    lineSelectionRef.current = { start: cursor.column, end: cursor.column };
    setActiveLine(cursor.line);
    setPreferredColumn(cursor.column);
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
    <div
      className="min-h-[60vh] cursor-text px-1 py-2"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          event.preventDefault();
          focusLine(Math.max(0, lines.length - 1));
        }
      }}
    >
      {documentMode ? (
        <textarea
          ref={documentInputRef}
          rows={Math.max(lines.length, 1)}
          className="block min-h-[60vh] w-full resize-none border-0 bg-transparent px-3 py-0.5 text-[15px] leading-7 text-stone-100 outline-none placeholder:text-stone-500"
          value={value}
          spellCheck={false}
          placeholder={placeholder}
          onBlur={(event) => {
            const { selectionStart, selectionEnd } = event.currentTarget;
            documentSelectionRef.current = { start: selectionStart, end: selectionEnd };
            if (selectionStart !== selectionEnd) {
              return;
            }
            setDocumentMode(false);
            setFocused(false);
          }}
          onSelect={(event) => {
            const { selectionStart, selectionEnd } = event.currentTarget;
            documentSelectionRef.current = { start: selectionStart, end: selectionEnd };
            syncCursorFromDocument(event.currentTarget.value, selectionStart);
          }}
          onChange={(event) => {
            const { selectionStart, selectionEnd, value: nextValue } = event.currentTarget;
            documentSelectionRef.current = { start: selectionStart, end: selectionEnd };
            syncCursorFromDocument(nextValue, selectionStart);
            onChange(nextValue);
            if (selectionStart === selectionEnd) {
              setDocumentMode(false);
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              setDocumentMode(false);
            }
          }}
        />
      ) : (
        renderBlocks.map((block) => {
          if (block.type === "details") {
            return (
              <div
                key={`details-${block.start}-${block.end}`}
                className="block w-full cursor-text select-text px-3 py-1 text-left text-inherit"
                onMouseUp={(event) => {
                  const selection = window.getSelection();
                  if (!selection?.isCollapsed || !shouldEnterEditMode(event.target)) {
                    return;
                  }
                  focusLine(block.start);
                }}
              >
                <MarkdownPreview markdown={block.markdown} />
              </div>
            );
          }

          const { index, line } = block;
          const isActive = focused && index === activeLine;
          const isBlank = line.trim().length === 0;
          const showEmptyPlaceholder = isBlank && isDocumentEmpty && index === 0 && !focused;

          return (
            <div
              key={`${index}-${line}`}
              className={cn(
                "min-h-7 px-3 py-0.5 text-[15px] leading-7 transition-colors duration-100",
                isActive && "text-stone-100",
              )}
            >
              {isActive ? (
                <textarea
                  ref={inputRef}
                  rows={1}
                  className="block min-h-[1.75rem] w-full resize-none border-0 bg-transparent p-0 text-[15px] leading-7 text-stone-100 outline-none placeholder:text-stone-500"
                  value={line}
                  spellCheck={false}
                  placeholder={placeholder}
                  onBlur={() => {
                    setFocused(false);
                  }}
                  onSelect={(event) => {
                    setLineSelection(event.currentTarget.selectionStart, event.currentTarget.selectionEnd);
                  }}
                  onChange={(event) => {
                    setLineSelection(event.target.selectionStart, event.target.selectionEnd);
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
                    const { selectionStart, selectionEnd, value: currentLineValue } = event.currentTarget;

                    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
                      event.preventDefault();
                      enterDocumentMode(0, value.length);
                      return;
                    }

                    if (event.key === "Enter") {
                      event.preventDefault();
                      const before = currentLineValue.slice(0, selectionStart);
                      const after = currentLineValue.slice(selectionEnd);
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
                      nextLines.splice(activeLine - 1, 2, `${previous}${currentLineValue}`);
                      setLineSelection(previous.length);
                      updateValue(nextLines, activeLine - 1, previous.length);
                      return;
                    }

                    if (
                      event.key === "Delete" &&
                      selectionStart === selectionEnd &&
                      selectionStart === currentLineValue.length &&
                      activeLine < lines.length - 1
                    ) {
                      event.preventDefault();
                      const following = lines[activeLine + 1] ?? "";
                      const nextLines = [...lines];
                      nextLines.splice(activeLine, 2, `${currentLineValue}${following}`);
                      setLineSelection(currentLineValue.length);
                      updateValue(nextLines, activeLine, currentLineValue.length);
                    }
                  }}
                />
              ) : (
                <div
                  className="block w-full cursor-text select-text p-0 text-left text-inherit"
                  onMouseUp={(event) => {
                    const selection = window.getSelection();
                    if (!selection?.isCollapsed || !shouldEnterEditMode(event.target)) {
                      return;
                    }
                    focusLine(index);
                  }}
                >
                  {showEmptyPlaceholder ? (
                    <span className="text-sm text-stone-500/80">{placeholder}</span>
                  ) : isBlank ? (
                    <span className="block min-h-[1.75rem]">&nbsp;</span>
                  ) : (
                    <MarkdownLine markdown={line} />
                  )}
                </div>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
