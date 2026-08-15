import { useCallback, useRef, useState, type DragEvent } from 'react'
import { UploadCloud, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'

const ACCEPTED_EXTENSIONS = ['.txt', '.pdf', '.docx']

interface DropzoneProps {
  onFileSelected: (file: File) => void
  selectedFile: File | null
  disabled?: boolean
}

export function Dropzone({ onFileSelected, selectedFile, disabled }: DropzoneProps) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const isAccepted = (file: File) => ACCEPTED_EXTENSIONS.some((ext) => file.name.toLowerCase().endsWith(ext))

  const handleFiles = useCallback(
    (files: FileList | null) => {
      const file = files?.[0]
      if (file && isAccepted(file)) onFileSelected(file)
    },
    [onFileSelected],
  )

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setIsDragging(true)
      }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) inputRef.current?.click()
      }}
      aria-disabled={disabled}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors duration-150',
        isDragging ? 'border-primary bg-primary/5' : 'border-border bg-muted/30 hover:border-border-strong',
        disabled && 'pointer-events-none opacity-60',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS.join(',')}
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
        disabled={disabled}
      />
      {selectedFile ? (
        <>
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <FileText className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">{selectedFile.name}</p>
            <p className="text-xs text-muted-foreground">{(selectedFile.size / 1024).toFixed(1)} KB · click to change</p>
          </div>
        </>
      ) : (
        <>
          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-primary/10 text-primary">
            <UploadCloud className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-semibold text-foreground">Drop a chapter file here, or click to browse</p>
            <p className="text-xs text-muted-foreground">Supports .txt, .pdf, .docx</p>
          </div>
        </>
      )}
    </div>
  )
}
