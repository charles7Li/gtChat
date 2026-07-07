import { useRef } from "react";

export function FileDropzone({ disabled, onFiles }: { disabled?: boolean; onFiles: (files: FileList) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div
      className={disabled ? "dropzone disabled" : "dropzone"}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        if (!disabled && event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
      }}
    >
      <input ref={inputRef} type="file" multiple disabled={disabled} onChange={(event) => event.target.files && onFiles(event.target.files)} />
      <strong>拖拽素材到这里</strong>
      <span>支持 video、image、CSV、JSON。XLSX 等拿到真实样本后再补。</span>
      <button type="button" disabled={disabled} onClick={() => inputRef.current?.click()}>
        Select files
      </button>
    </div>
  );
}
