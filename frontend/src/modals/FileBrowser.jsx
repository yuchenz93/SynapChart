import { useState, useEffect } from 'react';
import { browseFiles } from '../api/client';

/**
 * Modal file-browser that lets the user navigate the server filesystem
 * and select a file path. Double-clicking a file also selects it.
 *
 * Props:
 *   initialPath  – starting path (default: server home directory)
 *   onSelect(path) – called when the user confirms a selection
 *   onClose()      – called when the user dismisses the modal
 */
/** Join a directory path and a filename with the correct separator. */
function joinPath(dir, name) {
  if (!dir) return name;
  const sep = dir.includes('\\') ? '\\' : '/';
  return dir.endsWith(sep) ? dir + name : dir + sep + name;
}

/** Extract just the filename (last segment) from a full path. */
function baseName(p) {
  return p.replace(/.*[/\\]/, '');
}

export default function FileBrowser({ initialPath = '', onSelect, onClose, placeholder = 'File name…', autoExt = '' }) {
  const [currentPath, setCurrentPath] = useState('');
  const [parentPath, setParentPath]   = useState(null);
  const [entries, setEntries]         = useState([]);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  // fileName is the editable part; full path = currentPath + sep + fileName
  const [fileName, setFileName] = useState(baseName(initialPath));

  const navigate = async (path) => {
    setLoading(true);
    setError(null);
    try {
      const res = await browseFiles(path);
      setCurrentPath(res.current_path);
      setParentPath(res.parent_path);
      setEntries(res.entries);
    } catch (err) {
      setError(`Cannot open path: ${err.response?.data?.detail?.message ?? err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // On mount: if there's an existing value start in its directory, otherwise show drives/home
  useEffect(() => { navigate(initialPath || ''); }, []);

  const handleClick = (entry) => {
    if (entry.is_dir) {
      navigate(entry.path);
    } else {
      setFileName(entry.name);
    }
  };

  const handleDoubleClick = (entry) => {
    if (!entry.is_dir) onSelect(entry.path);
  };

  const handleSelect = () => {
    if (!fileName) return;
    // Auto-append extension if caller requested it and the name lacks one
    let name = fileName;
    if (autoExt && !name.toLowerCase().endsWith(autoExt.toLowerCase())) {
      name = name + autoExt;
    }
    // If the user typed a full absolute path, use it as-is; otherwise join with currentPath.
    const isAbsolute = /^[A-Za-z]:[/\\]/.test(name) || name.startsWith('/') || name.startsWith('\\\\');
    const resolved = isAbsolute ? name : joinPath(currentPath, name);
    onSelect(resolved);
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1100,
        background: 'rgba(0,0,0,0.65)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: '#1f2937', border: '1px solid #374151', borderRadius: 8,
          width: 580, height: 500, display: 'flex', flexDirection: 'column',
          color: '#f9fafb', boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', borderBottom: '1px solid #374151',
        }}>
          <span style={{ fontWeight: 600, fontSize: 14 }}>Browse Files</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>

        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '6px 12px', borderBottom: '1px solid #374151',
        }}>
          <button
            onClick={() => navigate('')}
            title="Show all drives"
            style={{
              background: '#374151', border: 'none', borderRadius: 4,
              color: '#f9fafb', padding: '3px 10px', cursor: 'pointer', fontSize: 12,
            }}
          >
            💾 Drives
          </button>
          <button
            onClick={() => parentPath != null && navigate(parentPath)}
            disabled={parentPath == null}
            style={{
              background: '#374151', border: 'none', borderRadius: 4,
              color: parentPath != null ? '#f9fafb' : '#4b5563',
              padding: '3px 10px', cursor: parentPath != null ? 'pointer' : 'default', fontSize: 12,
            }}
          >
            ↑ Up
          </button>
          <span style={{ flex: 1, fontSize: 11, color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {currentPath || 'Drives'}
          </span>
        </div>

        {/* File list */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {loading && (
            <div style={{ padding: '10px 16px', color: '#6b7280', fontSize: 12 }}>Loading…</div>
          )}
          {error && (
            <div style={{ padding: '10px 16px', color: '#ef4444', fontSize: 12 }}>{error}</div>
          )}
          {!loading && !error && entries.length === 0 && (
            <div style={{ padding: '10px 16px', color: '#6b7280', fontSize: 12 }}>Empty directory.</div>
          )}
          {!loading && !error && entries.map(entry => {
            const isSelected = !entry.is_dir && fileName === entry.name;
            return (
              <div
                key={entry.path}
                onClick={() => handleClick(entry)}
                onDoubleClick={() => handleDoubleClick(entry)}
                style={{
                  padding: '5px 16px', cursor: 'pointer', fontSize: 12,
                  display: 'flex', alignItems: 'center', gap: 8,
                  background: isSelected ? '#374151' : 'transparent',
                  color: entry.is_dir ? '#60a5fa' : '#f9fafb',
                  userSelect: 'none',
                }}
                onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = '#283548'; }}
                onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{ fontSize: 14 }}>{entry.is_dir ? '📁' : '📄'}</span>
                <span>{entry.name}</span>
              </div>
            );
          })}
        </div>

        {/* Footer: current folder (read-only) + filename input + Select */}
        <div style={{ padding: '8px 12px', borderTop: '1px solid #374151' }}>
          {/* Folder row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: '#6b7280', whiteSpace: 'nowrap' }}>Folder:</span>
            <span style={{
              flex: 1, fontSize: 11, color: '#9ca3af',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              background: '#111827', border: '1px solid #1f2937',
              borderRadius: 4, padding: '3px 6px',
            }}>
              {currentPath || '—'}
            </span>
          </div>
          {/* Filename row */}
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              value={fileName}
              onChange={e => setFileName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSelect()}
              placeholder={placeholder}
              style={{
                flex: 1, background: '#111827', border: '1px solid #374151',
                borderRadius: 4, color: '#f9fafb', padding: '5px 8px', fontSize: 12,
              }}
            />
            <button
              onClick={handleSelect}
              disabled={!fileName}
              style={{
                background: fileName ? '#4f46e5' : '#374151',
                border: 'none', borderRadius: 4, color: '#fff',
                padding: '5px 16px', cursor: fileName ? 'pointer' : 'default', fontSize: 12,
              }}
            >
              Select
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
