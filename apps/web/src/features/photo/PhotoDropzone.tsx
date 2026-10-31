import { type DragEvent, useId, useRef, useState } from "react";
import { ImageUp } from "lucide-react";
import { copy } from "@/copy";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function PhotoDropzone({
  onFile,
  onWrongType,
  disabled,
  describedBy,
}: {
  onFile: (file: File) => void;
  onWrongType: () => void;
  disabled?: boolean;
  /** id of an error shown next to the dropzone, read out with the button */
  describedBy?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const hintId = useId();

  const take = (file: File | undefined | null) => {
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      onWrongType();
      return;
    }
    onFile(file);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    if (!disabled) take(e.dataTransfer.files?.[0]);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      data-testid="dropzone"
      data-over={over || undefined}
      className={cn(
        "flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed bg-card px-6 py-10 text-center transition-colors sm:py-14",
        over ? "border-primary bg-accent" : "border-border-strong",
        disabled && "opacity-60",
      )}
    >
      <span className="grid size-16 place-items-center rounded-2xl bg-accent text-primary" aria-hidden="true">
        <ImageUp className="size-8" />
      </span>
      <p className="text-base font-semibold">{copy.photo.dropHere}</p>
      <p className="text-sm text-muted-foreground">{copy.photo.or}</p>
      <Button
        size="lg"
        onClick={() => inputRef.current?.click()}
        disabled={disabled}
        aria-describedby={[hintId, describedBy].filter(Boolean).join(" ")}
      >
        {copy.photo.choose}
      </Button>
      <p id={hintId} className="text-xs text-muted-foreground">
        {copy.photo.formats}
      </p>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        data-testid="photo-input"
        onChange={(e) => {
          take(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
    </div>
  );
}
