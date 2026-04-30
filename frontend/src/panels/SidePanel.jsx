import { useState, useRef, useEffect, useMemo } from 'react';
import usePipelineStore from '../store/pipelineStore';
import BlockWizard from '../modals/BlockWizard';
import LibraryManager from '../modals/LibraryManager';
import { getBlocks, getBlockSource, deleteBlock, updateBlockCategory, deleteCompositeBlock, getCompositeBlock, refreshLibraries } from '../api/client';

// Categories shipped with the application — cannot be renamed or deleted.
const BUILTIN_CATEGORIES = new Set(['Data I/O', 'Behavior', 'LFP / EEG', 'Spikes', 'Visualization', 'Flow control']);

// ── Shared style helpers ───────────────────────────────────────────────────────

const menuItemStyle = (disabled = false, danger = false) => ({
  display: 'block', width: '100%', textAlign: 'left',
  background: 'none', border: 'none',
  color: disabled ? '#4b5563' : danger ? '#f87171' : '#f9fafb',
  padding: '6px 14px', fontSize: 12,
  cursor: disabled ? 'default' : 'pointer',
  pointerEvents: disabled ? 'none' : 'auto',
});

const menuDivider = { height: 1, background: '#374151', margin: '4px 0' };

const menuHeader = (label) => (
  <div style={{ padding: '4px 12px 4px', color: '#9ca3af', fontSize: 10,
    fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em',
    borderBottom: '1px solid #374151', marginBottom: 3 }}>
    {label}
  </div>
);

// ── Component ─────────────────────────────────────────────────────────────────

/**
 * Collapsible left-side panel showing the block library grouped by category.
 * Blocks are draggable onto the canvas and can be reordered within their
 * category via drag-and-drop. Right-click menus on blocks and category headers
 * provide edit, delete, duplicate, rename, and new-category actions.
 */
export default function SidePanel() {
  const { blockLibrary, setBlockLibrary, openCompositeForEdit } = usePipelineStore(s => ({
    blockLibrary: s.blockLibrary,
    setBlockLibrary: s.setBlockLibrary,
    openCompositeForEdit: s.openCompositeForEdit,
  }));

  // ── UI state ──
  const [search, setSearch]         = useState('');
  const [collapsed, setCollapsed]   = useState({});
  const [libCollapsed, setLibCollapsed] = useState({});
  const [groupCollapsed, setGroupCollapsed] = useState({});
  const [showLibManager, setShowLibManager] = useState(false);

  // ── Wizard ──
  const [showWizard, setShowWizard]           = useState(false);
  const [wizardEditBlock, setWizardEditBlock] = useState(null);
  const [wizardSaveToLib, setWizardSaveToLib] = useState(false);

  // ── Block context menu: { x, y, block } ──
  const [blockMenu, setBlockMenu] = useState(null);
  const blockMenuRef = useRef(null);

  // ── Category context menu: { x, y, catName } ──
  const [catMenu, setCatMenu] = useState(null);
  const catMenuRef = useRef(null);

  // ── Inline category rename ──
  const [renamingCat, setRenamingCat] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const renameInputRef = useRef(null);

  // ── D&D reorder + cross-category move ──
  const [dragging, setDragging]       = useState(null);  // { blockTypeId, catName }
  const [dragOver, setDragOver]       = useState(null);  // { blockTypeId, catName, position } — within-cat indicator
  const [catDragOver, setCatDragOver] = useState(null);  // catName — cross-cat drop target

  // ── Library view ──
  const query = search.toLowerCase();

  // displayLibraries: [{id, name, group, is_builtin, categories: [{name, blocks}]}]
  // When searching: only include libraries/categories/blocks that match
  const displayLibraries = useMemo(() => {
    if (!search) return blockLibrary;
    return blockLibrary
      .map(lib => ({
        ...lib,
        categories: (lib.categories ?? [])
          .map(cat => ({
            ...cat,
            blocks: (cat.blocks ?? []).filter(b =>
              b.display_name.toLowerCase().includes(query) ||
              (b.description ?? '').toLowerCase().includes(query)
            ),
          }))
          .filter(cat => cat.blocks.length > 0),
      }))
      .filter(lib => lib.categories.length > 0);
  }, [blockLibrary, search, query]);

  // Group libraries by their group field for rendering.
  // Libraries without a group are placed in a "" bucket and rendered ungrouped.
  const groupedLibraries = useMemo(() => {
    const groups = {};
    for (const lib of displayLibraries) {
      const g = lib.group ?? '';
      if (!groups[g]) groups[g] = [];
      groups[g].push(lib);
    }
    // Grouped ones first (sorted by group name), then ungrouped at the end
    const result = [];
    const groupNames = Object.keys(groups).filter(g => g).sort();
    for (const g of groupNames) result.push({ groupName: g, libs: groups[g] });
    if (groups['']) result.push({ groupName: '', libs: groups[''] });
    return result;
  }, [displayLibraries]);

  // Flat categories across all libraries — for backward-compat D&D / category ops.
  // Maps category name → library id so we know which library owns it.
  const catLibMap = useMemo(() => {
    const m = {};
    for (const lib of blockLibrary) {
      for (const cat of lib.categories ?? []) {
        m[cat.name] = lib.id;
      }
    }
    return m;
  }, [blockLibrary]);

  // Helper: update categories of a specific library in blockLibrary
  const updateLibraryCategories = (libraryId, updater) => {
    setBlockLibrary(blockLibrary.map(lib =>
      lib.id === libraryId
        ? { ...lib, categories: updater(lib.categories ?? []) }
        : lib
    ));
  };

  // ── Close menus on outside click ──
  useEffect(() => {
    if (!blockMenu && !catMenu) return;
    const handler = (e) => {
      if (blockMenuRef.current && !blockMenuRef.current.contains(e.target)) setBlockMenu(null);
      if (catMenuRef.current  && !catMenuRef.current.contains(e.target))  setCatMenu(null);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [blockMenu, catMenu]);

  // ── Auto-focus rename input ──
  useEffect(() => {
    if (renamingCat && renameInputRef.current) {
      renameInputRef.current.focus();
      renameInputRef.current.select();
    }
  }, [renamingCat]);

  // ── Block menu actions ────────────────────────────────────────────────────

  const openBlockMenu = (e, block) => {
    e.preventDefault();
    setBlockMenu({ x: e.clientX, y: e.clientY, block });
    setCatMenu(null);
  };

  const handleEditBlock = (block) => {
    setWizardEditBlock(block);
    setWizardSaveToLib(false);
    setShowWizard(true);
    setBlockMenu(null);
  };

  // Edit a built-in block: fetch source, strip namespace from ID, open wizard in
  // edit mode (is_custom: true) so the wizard calls updateBlock → writes to disk.
  const handleEditBuiltinBlock = async (block) => {
    setBlockMenu(null);
    try {
      const res = await getBlockSource(block.block_type_id);
      const shortId = block.block_type_id.includes('.')
        ? block.block_type_id.split('.').pop()
        : block.block_type_id;
      setWizardEditBlock({
        ...block,
        block_type_id:  shortId,
        is_custom:      true,          // force isEdit=true in the wizard
        source_snippet: res.source_snippet ?? null,
      });
      setWizardSaveToLib(false);
      setShowWizard(true);
    } catch (err) {
      alert(`Could not load block source: ${err.message}`);
    }
  };

  const handleDeleteBlock = async (block) => {
    setBlockMenu(null);
    if (!window.confirm(`Delete "${block.display_name}" from the library?\nThis removes the block file and cannot be undone.`)) return;
    try {
      await deleteBlock(block.block_type_id);
      const data = await getBlocks();
      setBlockLibrary(data.libraries ?? []);
    } catch (err) {
      alert(`Delete failed: ${err.response?.data?.detail?.message ?? err.message}`);
    }
  };

  const handleEditComposite = async (block) => {
    setBlockMenu(null);
    try {
      const definition = await getCompositeBlock(block.block_type_id);
      openCompositeForEdit(definition);
    } catch (err) {
      alert(`Failed to open composite: ${err.response?.data?.detail?.message ?? err.message}`);
    }
  };

  const handleDeleteComposite = async (block) => {
    setBlockMenu(null);
    if (!window.confirm(`Delete composite block "${block.display_name}" from the library?\nWorkflows that have already imported it remain unaffected (copy semantics).`)) return;
    try {
      await deleteCompositeBlock(block.block_type_id);
      const data = await getBlocks();
      setBlockLibrary(data.libraries ?? []);
    } catch (err) {
      alert(`Delete failed: ${err.response?.data?.detail?.message ?? err.message}`);
    }
  };

  const handleDuplicateBlock = async (block) => {
    setBlockMenu(null);
    try {
      const res = await getBlockSource(block.block_type_id);
      // Build a pre-filled create-mode editBlock (no is_custom → new block mode in wizard).
      setWizardEditBlock({
        ...block,
        display_name:   `${block.display_name} (copy)`,
        block_type_id:  `${block.block_type_id}_copy`,
        is_custom:      false,
        source_snippet: res.source_snippet ?? null,
      });
      setWizardSaveToLib(true);  // duplicate goes to global library
      setShowWizard(true);
    } catch (err) {
      alert(`Could not load block source: ${err.message}`);
    }
  };

  // ── Category menu actions ────────────────────────────────────────────────

  const openCatMenu = (e, catName) => {
    e.preventDefault();
    e.stopPropagation();    // don't also toggle collapse
    setCatMenu({ x: e.clientX, y: e.clientY, catName });
    setBlockMenu(null);
  };

  const startRenameCategory = (catName) => {
    setCatMenu(null);
    setRenamingCat(catName);
    setRenameValue(catName);
  };

  const commitRename = () => {
    const newName = renameValue.trim();
    if (!newName || newName === renamingCat) { cancelRename(); return; }
    const libId = catLibMap[renamingCat];
    if (!libId) { cancelRename(); return; }
    updateLibraryCategories(libId, cats => cats.map(c =>
      c.name === renamingCat
        ? { ...c, name: newName, blocks: (c.blocks ?? []).map(b => ({ ...b, category: newName })) }
        : c
    ));
    setCollapsed(prev => {
      const next = { ...prev };
      next[newName] = prev[renamingCat];
      delete next[renamingCat];
      return next;
    });
    setRenamingCat(null);
  };

  const cancelRename = () => setRenamingCat(null);

  const handleDeleteCategory = (catName) => {
    setCatMenu(null);
    const libId = catLibMap[catName];
    if (!libId) return;
    const lib = blockLibrary.find(l => l.id === libId);
    const cat = (lib?.categories ?? []).find(c => c.name === catName);
    if ((cat?.blocks ?? []).length > 0) {
      alert(`"${catName}" is not empty. Delete or move all blocks first.`);
      return;
    }
    updateLibraryCategories(libId, cats => cats.filter(c => c.name !== catName));
  };

  const handleNewCategory = (targetLibId) => {
    setCatMenu(null);
    // Default to user_blocks library, or the first non-builtin library
    const libId = targetLibId ?? blockLibrary.find(l => !l.is_builtin)?.id ?? 'user_blocks';
    const lib = blockLibrary.find(l => l.id === libId);
    const existingNames = new Set((lib?.categories ?? []).map(c => c.name));
    let name = 'New Category';
    let i = 2;
    while (existingNames.has(name)) name = `New Category ${i++}`;
    updateLibraryCategories(libId, cats => [...cats, { name, blocks: [] }]);
    setRenamingCat(name);
    setRenameValue(name);
  };

  // ── D&D reorder + cross-category move ───────────────────────────────────

  const onBlockDragStart = (e, block, catName) => {
    // Always set the canvas-drop MIME type so dragging to canvas still works.
    e.dataTransfer.setData('application/synapchart-block', block.block_type_id);
    // Mark composite blocks so the canvas drop handler can fetch & embed the full definition.
    if (block.is_composite) {
      e.dataTransfer.setData('application/synapchart-composite', 'true');
    }
    e.dataTransfer.effectAllowed = 'copyMove';
    // Only enable panel D&D when search is not active (filtered order is ambiguous).
    if (!search) setDragging({ blockTypeId: block.block_type_id, catName, isCustom: !!block.is_custom });
  };

  const onBlockDragOver = (e, block, catName) => {
    if (!dragging) return;
    e.preventDefault();
    if (dragging.catName !== catName) {
      // Cross-category: highlight the whole category, not individual blocks
      if (catDragOver !== catName) setCatDragOver(catName);
      setDragOver(null);
      return;
    }
    setCatDragOver(null);
    const rect = e.currentTarget.getBoundingClientRect();
    const position = e.clientY < rect.top + rect.height / 2 ? 'before' : 'after';
    if (dragOver?.blockTypeId !== block.block_type_id || dragOver?.position !== position) {
      setDragOver({ blockTypeId: block.block_type_id, catName, position });
    }
  };

  const onBlockDragLeave = (e) => {
    // Only clear if leaving the block row entirely (not moving to a child element)
    if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(null);
  };

  const onCategoryDragOver = (e, catName) => {
    if (!dragging || dragging.catName === catName) return;
    e.preventDefault();
    e.stopPropagation();
    if (catDragOver !== catName) setCatDragOver(catName);
  };

  const onCategoryDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setCatDragOver(null);
  };

  // Shared logic: move a block to another category (optimistic + backend persist).
  const moveBlockToCategory = async (blockTypeId, fromCat, toCat) => {
    if (!blockTypeId || fromCat === toCat) return;
    const fromLibId = catLibMap[fromCat];
    const toLibId   = catLibMap[toCat];
    if (!fromLibId) return;

    // Find the block
    const fromLib = blockLibrary.find(l => l.id === fromLibId);
    const fromCatObj = (fromLib?.categories ?? []).find(c => c.name === fromCat);
    const block = (fromCatObj?.blocks ?? []).find(b => b.block_type_id === blockTypeId);
    if (!block) return;

    const updatedBlock = { ...block, category: toCat };

    // Optimistic update — remove from source library/category, add to destination
    setBlockLibrary(blockLibrary.map(lib => {
      const newCats = (lib.categories ?? []).map(cat => {
        if (cat.name === fromCat && lib.id === fromLibId)
          return { ...cat, blocks: cat.blocks.filter(b => b.block_type_id !== blockTypeId) };
        if (cat.name === toCat && (toLibId ? lib.id === toLibId : true))
          return { ...cat, blocks: [...(cat.blocks ?? []), updatedBlock] };
        return cat;
      });
      return { ...lib, categories: newCats };
    }));

    // Persist for custom blocks
    if (block.is_custom) {
      try {
        await updateBlockCategory(blockTypeId, toCat);
      } catch (err) {
        const data = await getBlocks();
        setBlockLibrary(data.libraries ?? []);
        alert(`Could not move block: ${err.response?.data?.detail?.message ?? err.message}`);
      }
    }
  };

  const onBlockDrop = async (e, targetBlock, catName) => {
    e.preventDefault();
    if (!dragging) { setDragging(null); setDragOver(null); setCatDragOver(null); return; }

    if (dragging.catName !== catName) {
      // Cross-category drop on a block row → move to this category
      await moveBlockToCategory(dragging.blockTypeId, dragging.catName, catName);
      setDragging(null); setDragOver(null); setCatDragOver(null);
      return;
    }

    // Same-category reorder
    if (!dragOver) { setDragging(null); setDragOver(null); return; }
    const libId = catLibMap[catName];
    if (!libId) { setDragging(null); setDragOver(null); return; }
    setBlockLibrary(blockLibrary.map(lib => {
      if (lib.id !== libId) return lib;
      return {
        ...lib,
        categories: (lib.categories ?? []).map(cat => {
          if (cat.name !== catName) return cat;
          const blocks = [...(cat.blocks ?? [])];
          const fromIdx = blocks.findIndex(b => b.block_type_id === dragging.blockTypeId);
          if (fromIdx === -1) return cat;
          const [moved] = blocks.splice(fromIdx, 1);
          const toIdx = blocks.findIndex(b => b.block_type_id === targetBlock.block_type_id);
          if (toIdx === -1) { blocks.push(moved); }
          else blocks.splice(dragOver.position === 'before' ? toIdx : toIdx + 1, 0, moved);
          return { ...cat, blocks };
        }),
      };
    }));
    setDragging(null); setDragOver(null);
  };

  const onCategoryDrop = async (e, catName) => {
    e.preventDefault();
    e.stopPropagation();
    if (!dragging || dragging.catName === catName) { setDragging(null); setCatDragOver(null); return; }
    await moveBlockToCategory(dragging.blockTypeId, dragging.catName, catName);
    setDragging(null); setDragOver(null); setCatDragOver(null);
  };

  const onBlockDragEnd = () => { setDragging(null); setDragOver(null); setCatDragOver(null); };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      {/* ── BlockWizard ── */}
      {showWizard && (
        <BlockWizard
          editBlock={wizardEditBlock}
          saveToLibrary={wizardSaveToLib}
          onClose={() => { setShowWizard(false); setWizardEditBlock(null); setWizardSaveToLib(false); }}
        />
      )}

      {/* ── Block context menu ── */}
      {blockMenu && (
        <div ref={blockMenuRef} style={{
          position: 'fixed', top: blockMenu.y, left: blockMenu.x,
          background: '#1f2937', border: '1px solid #374151', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)', zIndex: 9999, minWidth: 190, padding: '4px 0',
        }}>
          {menuHeader(blockMenu.block.display_name)}

          {/* Composite blocks */}
          {blockMenu.block.is_composite ? (
            <>
              <button style={menuItemStyle()}
                onClick={() => handleEditComposite(blockMenu.block)}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                ✏ Edit composite
              </button>
              <div style={menuDivider} />
              <button style={menuItemStyle(false, true)}
                onClick={() => handleDeleteComposite(blockMenu.block)}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                ✕ Delete composite block
              </button>
            </>
          ) : (
            <>
              {/* Edit block definition — works for both custom and built-in */}
              <button style={menuItemStyle()}
                onClick={() => blockMenu.block.is_custom
                  ? handleEditBlock(blockMenu.block)
                  : handleEditBuiltinBlock(blockMenu.block)
                }
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                ✏ Edit block definition
                {!blockMenu.block.is_custom && (
                  <span style={{ fontSize: 10, marginLeft: 6, color: '#a78bfa' }}>(built-in)</span>
                )}
              </button>

              {/* Duplicate block */}
              <button style={menuItemStyle()}
                onClick={() => handleDuplicateBlock(blockMenu.block)}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                ⊕ Duplicate block
              </button>

              <div style={menuDivider} />

              {/* Delete block */}
              {blockMenu.block.is_custom ? (
                <button style={menuItemStyle(false, true)}
                  onClick={() => handleDeleteBlock(blockMenu.block)}
                  onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                  ✕ Delete block
                </button>
              ) : (
                <div style={{ ...menuItemStyle(true), padding: '6px 14px', fontSize: 12 }}>
                  ✕ Cannot delete built-in block
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Category context menu ── */}
      {catMenu && (
        <div ref={catMenuRef} style={{
          position: 'fixed', top: catMenu.y, left: catMenu.x,
          background: '#1f2937', border: '1px solid #374151', borderRadius: 6,
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)', zIndex: 9999, minWidth: 190, padding: '4px 0',
        }}>
          {menuHeader(catMenu.catName)}

          {/* New category */}
          <button style={menuItemStyle()}
            onClick={() => handleNewCategory()}
            onMouseEnter={e => e.currentTarget.style.background = '#374151'}
            onMouseLeave={e => e.currentTarget.style.background = 'none'}>
            ＋ New category
          </button>

          <div style={menuDivider} />

          {/* Rename */}
          {BUILTIN_CATEGORIES.has(catMenu.catName) ? (
            <div style={{ ...menuItemStyle(true), padding: '6px 14px', fontSize: 12 }}>
              ✎ Rename category
              <span style={{ fontSize: 10, marginLeft: 6, color: '#6b7280' }}>(built-in)</span>
            </div>
          ) : (
            <button style={menuItemStyle()}
              onClick={() => startRenameCategory(catMenu.catName)}
              onMouseEnter={e => e.currentTarget.style.background = '#374151'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}>
              ✎ Rename category
            </button>
          )}

          {/* Delete */}
          {(() => {
            const cat = blockLibrary.find(c => c.name === catMenu.catName);
            const isEmpty = (cat?.blocks ?? []).length === 0;
            const isBuiltin = BUILTIN_CATEGORIES.has(catMenu.catName);
            const canDelete = isEmpty && !isBuiltin;
            return canDelete ? (
              <button style={menuItemStyle(false, true)}
                onClick={() => handleDeleteCategory(catMenu.catName)}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                ✕ Delete category
              </button>
            ) : (
              <div style={{ ...menuItemStyle(true), padding: '6px 14px', fontSize: 12 }}>
                ✕ Delete category
                <span style={{ fontSize: 10, marginLeft: 4, color: '#6b7280' }}>
                  {isBuiltin ? '(built-in)' : '(not empty)'}
                </span>
              </div>
            );
          })()}
        </div>
      )}

      {/* ── Panel ── */}
      <div style={{
        width: 220, borderRight: '1px solid #374151',
        background: '#111827', color: '#f9fafb',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden', flexShrink: 0,
      }}>
        {/* New Block button */}
        <div style={{ padding: '8px 8px 0', display: 'flex', gap: 4 }}>
          <button
            onClick={() => { setWizardEditBlock(null); setWizardSaveToLib(false); setShowWizard(true); }}
            style={{ flex: 1, background: '#2563eb', border: 'none', borderRadius: 4,
              color: '#fff', padding: '6px 8px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
            onMouseEnter={e => e.currentTarget.style.background = '#1d4ed8'}
            onMouseLeave={e => e.currentTarget.style.background = '#2563eb'}
          >
            ＋ New block
          </button>
          <button
            onClick={() => setShowLibManager(true)}
            title="Manage libraries"
            style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 4,
              color: '#9ca3af', padding: '6px 8px', fontSize: 12, cursor: 'pointer' }}
            onMouseEnter={e => e.currentTarget.style.background = '#374151'}
            onMouseLeave={e => e.currentTarget.style.background = '#1f2937'}
          >
            📚
          </button>
        </div>

        {/* Search */}
        <div style={{ padding: '8px' }}>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search blocks…"
            style={{ width: '100%', background: '#1f2937', border: '1px solid #374151',
              borderRadius: 4, color: '#f9fafb', padding: '4px 8px', fontSize: 12,
              boxSizing: 'border-box' }}
          />
        </div>

        {/* Block list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {displayLibraries.length === 0 && search && (
            <p style={{ color: '#6b7280', fontSize: 12, padding: '8px 12px' }}>No blocks found.</p>
          )}

          {groupedLibraries.map(({ groupName, libs }) => (
            <div key={groupName || '__ungrouped__'}>
              {/* ── Group header (only when there is a group name) ── */}
              {groupName && (
                <button
                  onClick={() => setGroupCollapsed(prev => ({ ...prev, [groupName]: !prev[groupName] }))}
                  style={{
                    width: '100%', textAlign: 'left', border: 'none',
                    borderBottom: '2px solid #1e40af', borderTop: '1px solid #1e3a5f',
                    background: '#0a1628', color: '#93c5fd', fontSize: 10,
                    fontWeight: 800, padding: '6px 10px', cursor: 'pointer',
                    letterSpacing: '0.08em', textTransform: 'uppercase', userSelect: 'none',
                    display: 'flex', alignItems: 'center', gap: 5,
                  }}
                >
                  <span>{groupCollapsed[groupName] ? '▶' : '▼'}</span>
                  <span>🧠 {groupName}</span>
                </button>
              )}

              {/* ── Libraries within this group ── */}
              {!groupCollapsed[groupName] && libs.map(lib => (
            <div key={lib.id}>
              {/* ── Library header ── */}
              <button
                onClick={() => setLibCollapsed(prev => ({ ...prev, [lib.id]: !prev[lib.id] }))}
                style={{
                  width: '100%', textAlign: 'left', border: 'none',
                  borderBottom: '1px solid #1e3a5f', borderTop: '1px solid #374151',
                  background: groupName ? '#0d1f3c' : '#0f172a', color: '#60a5fa', fontSize: 10,
                  fontWeight: 700, padding: '5px 10px', cursor: 'pointer',
                  paddingLeft: groupName ? 20 : 10,
                  letterSpacing: '0.06em', textTransform: 'uppercase', userSelect: 'none',
                  display: 'flex', alignItems: 'center', gap: 5,
                }}
              >
                <span>{libCollapsed[lib.id] ? '▶' : '▼'}</span>
                <span>📦 {lib.name}</span>
                {lib.is_builtin && (
                  <span style={{ marginLeft: 'auto', fontSize: 9, color: '#374151',
                    background: '#1e293b', borderRadius: 2, padding: '0 4px' }}>built-in</span>
                )}
              </button>

              {/* ── Categories within this library ── */}
              {!libCollapsed[lib.id] && (lib.categories ?? []).map(cat => (
                <div key={`${lib.id}::${cat.name}`}>
                  {/* Category header */}
                  <div
                    style={{ display: 'flex', alignItems: 'stretch' }}
                    onDragOver={e => onCategoryDragOver(e, cat.name)}
                    onDragLeave={onCategoryDragLeave}
                    onDrop={e => onCategoryDrop(e, cat.name)}
                  >
                    {renamingCat === cat.name ? (
                      <input
                        ref={renameInputRef}
                        value={renameValue}
                        onChange={e => setRenameValue(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={e => {
                          if (e.key === 'Enter') commitRename();
                          if (e.key === 'Escape') cancelRename();
                          e.stopPropagation();
                        }}
                        style={{ flex: 1, background: '#0f172a', border: '1px solid #6366f1',
                          color: '#f9fafb', fontSize: 11, fontWeight: 700, padding: '5px 10px',
                          outline: 'none', textTransform: 'uppercase', letterSpacing: '0.05em' }}
                      />
                    ) : (
                      <button
                        onClick={() => setCollapsed(prev => ({ ...prev, [cat.name]: !prev[cat.name] }))}
                        onContextMenu={e => openCatMenu(e, cat.name)}
                        style={{
                          flex: 1, textAlign: 'left', border: 'none',
                          borderBottom: '1px solid #374151', color: '#9ca3af', fontSize: 11,
                          fontWeight: 700, padding: '5px 16px', cursor: 'pointer',
                          letterSpacing: '0.05em', textTransform: 'uppercase', userSelect: 'none',
                          background: catDragOver === cat.name ? '#1e3a5f' : '#1f2937',
                          outline: catDragOver === cat.name ? '1px solid #3b82f6' : 'none',
                          transition: 'background 0.1s',
                        }}
                      >
                        {catDragOver === cat.name ? '⊕ ' : (collapsed[cat.name] ? '▶ ' : '▼ ')}{cat.name}
                      </button>
                    )}
                  </div>

                  {/* Block entries */}
                  {!collapsed[cat.name] && (cat.blocks ?? []).length === 0 && (
                    <div style={{ padding: '5px 20px', fontSize: 11, color: '#4b5563', fontStyle: 'italic' }}>
                      Empty category
                    </div>
                  )}

                  {!collapsed[cat.name] && (cat.blocks ?? []).map(block => {
                    const isDraggingThis = dragging?.blockTypeId === block.block_type_id;
                    const isOverBefore   = dragOver?.blockTypeId === block.block_type_id && dragOver?.catName === cat.name && dragOver?.position === 'before';
                    const isOverAfter    = dragOver?.blockTypeId === block.block_type_id && dragOver?.catName === cat.name && dragOver?.position === 'after';

                    return (
                      <div key={block.block_type_id} style={{ position: 'relative' }}>
                        {isOverBefore && <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: '#6366f1', zIndex: 2 }} />}
                        {isOverAfter  && <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 2, background: '#6366f1', zIndex: 2 }} />}

                        <div
                          draggable
                          onDragStart={e => onBlockDragStart(e, block, cat.name)}
                          onDragOver={e  => onBlockDragOver(e, block, cat.name)}
                          onDragLeave={onBlockDragLeave}
                          onDrop={e      => onBlockDrop(e, block, cat.name)}
                          onDragEnd={onBlockDragEnd}
                          onContextMenu={e => openBlockMenu(e, block)}
                          title={block.description}
                          style={{
                            padding: '6px 20px',
                            cursor: 'grab', fontSize: 12,
                            borderBottom: '1px solid #1f2937',
                            userSelect: 'none', display: 'flex', alignItems: 'center', gap: 6,
                            opacity: isDraggingThis ? 0.35 : 1, transition: 'opacity 0.1s',
                          }}
                          onMouseEnter={e => e.currentTarget.style.background = '#1f2937'}
                          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >
                          <span style={{ flex: 1 }}>{block.display_name}</span>
                          {block.is_composite && (
                            <span title="Composite block" style={{ fontSize: 9, color: '#a5b4fc',
                              border: '1px solid #6366f1', borderRadius: 3, padding: '0 3px', lineHeight: '14px' }}>
                              ⊞
                            </span>
                          )}
                          {block.is_custom && !block.is_composite && (
                            <span title="Custom block" style={{ fontSize: 9, color: '#6366f1',
                              border: '1px solid #6366f1', borderRadius: 3, padding: '0 3px', lineHeight: '14px' }}>
                              custom
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
              ))}
            </div>
          ))}

          {/* Refresh button at the bottom */}
          <div style={{ padding: '8px', borderTop: '1px solid #1f2937', marginTop: 4 }}>
            <button
              onClick={async () => {
                try {
                  await refreshLibraries();
                  const data = await getBlocks();
                  setBlockLibrary(data.libraries ?? []);
                } catch (err) {
                  console.error('Refresh failed:', err);
                }
              }}
              style={{ width: '100%', background: 'none', border: '1px solid #374151',
                borderRadius: 4, color: '#6b7280', padding: '4px 8px', fontSize: 11,
                cursor: 'pointer' }}
              onMouseEnter={e => e.currentTarget.style.color = '#9ca3af'}
              onMouseLeave={e => e.currentTarget.style.color = '#6b7280'}
            >
              ↺ Refresh libraries
            </button>
          </div>
        </div>
      </div>

      {/* Library Manager Modal */}
      {showLibManager && (
        <LibraryManager onClose={() => setShowLibManager(false)} />
      )}
    </>
  );
}
