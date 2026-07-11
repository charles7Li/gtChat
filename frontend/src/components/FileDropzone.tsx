import { DragEvent } from "react";

export function FileDropzone({ disabled, onFiles }: { disabled: boolean; onFiles: (files: FileList) => void }) {
  function drop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (!disabled && event.dataTransfer.files.length) onFiles(event.dataTransfer.files);
  }

  return (
    <label className={`dropzone${disabled ? " disabled" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={drop}>
      <span className="logo-placeholder quiet" aria-hidden="true" />
      <strong>拖入文件，或点击选择</strong>
      <span>支持视频、图片、CSV 与 JSON；文件只在本地处理。</span>
      <input type="file" multiple disabled={disabled} onChange={(event) => event.target.files && onFiles(event.target.files)} />
    </label>
  );
}
