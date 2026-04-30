import usePipelineStore from '../store/pipelineStore';

export default function TabBar() {
  const { tabs, activeTabId, addTab, switchTab, closeTab } = usePipelineStore();

  const handleClose = (e, tab) => {
    e.stopPropagation();
    if (tab.isDirty) {
      if (!window.confirm(`"${tab.label}" has unsaved changes. Close anyway?`)) return;
    }
    closeTab(tab.id);
  };

  return (
    <div style={{
      display: 'flex', alignItems: 'stretch',
      background: '#0f172a', borderBottom: '1px solid #374151',
      overflowX: 'auto', flexShrink: 0, height: 32,
      // Hide scrollbar but keep scrollability
      scrollbarWidth: 'none',
    }}>
      {tabs.map(tab => {
        const isActive = tab.id === activeTabId;
        return (
          <div
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '0 10px', cursor: 'pointer',
              borderRight: '1px solid #1e293b',
              fontSize: 12, userSelect: 'none',
              minWidth: 0, maxWidth: 200,
              background: isActive ? '#1e293b' : 'transparent',
              color: isActive ? '#f9fafb' : '#6b7280',
              borderTop: isActive ? '2px solid #6366f1' : '2px solid transparent',
              position: 'relative',
            }}
            title={tab.filePath ?? tab.label}
          >
            <span style={{
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              flex: 1,
            }}>
              {tab.compositeEditId && (
                <span style={{ marginRight: 4, fontSize: 10, color: '#818cf8' }}>⊞</span>
              )}
              {tab.label}
              {tab.isDirty && (
                <span style={{ color: '#f59e0b', marginLeft: 3 }}>●</span>
              )}
            </span>
            <span
              onClick={e => handleClose(e, tab)}
              title="Close tab"
              style={{
                flexShrink: 0, width: 16, height: 16,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                borderRadius: 3, fontSize: 11, lineHeight: 1,
                color: '#6b7280',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = '#374151';
                e.currentTarget.style.color = '#f9fafb';
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'transparent';
                e.currentTarget.style.color = '#6b7280';
              }}
            >
              ✕
            </span>
          </div>
        );
      })}

      {/* New tab button */}
      <div
        onClick={addTab}
        title="New tab"
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          width: 32, cursor: 'pointer', flexShrink: 0,
          color: '#6b7280', fontSize: 18, lineHeight: 1,
          borderTop: '2px solid transparent',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.color = '#f9fafb';
          e.currentTarget.style.background = '#1e293b';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.color = '#6b7280';
          e.currentTarget.style.background = 'transparent';
        }}
      >
        +
      </div>
    </div>
  );
}
