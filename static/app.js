'use strict';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async post(url, body) {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async put(url, body) {
    const r = await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
    return r.json();
  },
  async delete(url) {
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error((await r.json()).detail || r.statusText);
    return r.status !== 204 ? r.json() : null;
  },
};

// ---------------------------------------------------------------------------
// Root Alpine component
// ---------------------------------------------------------------------------
function profileEditor() {
  return {
    // ---- Reference data ----
    refDatatypes: [],
    refSegments: [],
    hl7Versions: [],
    usageCodes: [],
    dtSearch: '',

    // ---- Profile list ----
    profiles: [],
    selectedProfileId: '',

    // ---- Current profile ----
    currentProfile: null,

    // ---- Segment tree ----
    selectedSegmentName: null,
    treeNodes: [],   // flattened [{id, label, type, depth, segmentName}]

    // ---- Field table ----
    get selectedSegment() {
      if (!this.currentProfile || !this.selectedSegmentName) return null;
      return this._findSegment(this.currentProfile.structure, this.selectedSegmentName);
    },
    get selectedSegmentFields() {
      if (!this.selectedSegment) return [];
      return [...(this.selectedSegment.fields || [])].sort((a, b) => a.seq - b.seq);
    },

    // ---- Modals ----
    showNewProfileModal: false,
    newProfile: { message_type: '', trigger_event: '', hl7_version: '2.7', description: '', author: '', name: '' },

    // ---- HL7 Standard import ----
    importMode: 'blank',       // 'blank' | 'standard'
    hl7stdEvents: [],
    hl7stdEventId: '',
    hl7stdEventFilter: '',
    loadingHl7stdEvents: false,
    importingFromStandard: false,
    importProgress: '',
    get filteredHl7stdEvents() {
      const q = this.hl7stdEventFilter.toLowerCase();
      if (!q) return this.hl7stdEvents;
      return this.hl7stdEvents.filter(e =>
        e.id.toLowerCase().includes(q) || (e.label || '').toLowerCase().includes(q)
      );
    },

    showDuplicateModal: false,
    duplicateName: '',
    duplicateMsgType: '',
    duplicateTrigger: '',

    showRenameModal: false,
    renameName: '',
    renameMsgType: '',
    renameTrigger: '',

    // ---- Shared segments library ----
    sharedSegments: [],
    sharedSegmentFilter: '',
    showSharedPanel: false,
    showSaveSharedModal: false,
    saveSharedId: '',
    saveSharedDesc: '',
    get filteredSharedSegments() {
      const q = this.sharedSegmentFilter.toLowerCase();
      if (!q) return this.sharedSegments;
      return this.sharedSegments.filter(s =>
        s.id.toLowerCase().includes(q) || s.segment_name.toLowerCase().includes(q)
      );
    },

    showSegmentModal: false,
    newSegment: { segment: '', usage: 'O', min: 0, max: 1, description: '' },
    segmentModalTab: 'new',  // 'new' | 'shared'

    showEditSegmentModal: false,
    editSegment: { segment: '', usage: 'O', min: 0, max: '*', description: '' },
    segmentSearch: '',
    get filteredSegments() {
      const q = this.segmentSearch.toLowerCase();
      return this.refSegments.filter(s =>
        s.code.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
      );
    },

    fieldEditorOpen: false,
    editingField: null,  // null = new
    fieldForm: { seq: null, name: '', datatype: 'ST', usage: 'O', repeatable: false, min_length: 0, max_length: 999, description: '', notes: '', value_set: '', format_pattern: '', format_preset: '' },
    formatPresets: [
      { label: 'DTM',      group: 'datetime', pattern: '\\d{8}(\\d{2}(\\d{2}(\\d{2})?)?)?([-+]\\d{4})?', description: 'HL7 date/time',     example: '20241231, 20241231143000, 20241231143000+0200' },
      { label: 'DATE',     group: 'datetime', pattern: '\\d{8}',                                           description: 'Date only',          example: '20241231' },
      { label: 'DATE-ISO', group: 'datetime', pattern: '\\d{4}-\\d{2}-\\d{2}',                             description: 'ISO date',           example: '2024-12-31' },
      { label: 'TIME',     group: 'datetime', pattern: '\\d{4}(\\d{2})?',                                  description: 'Time HHMM[SS]',      example: '1430, 143000' },
      { label: 'NM',       group: 'numeric',  pattern: '-?\\d+(\\.\\d+)?',                                 description: 'Number',             example: '42, -3.14, 0.5' },
      { label: 'SI',       group: 'numeric',  pattern: '\\d+',                                             description: 'Positive integer',   example: '1, 99, 1000' },
      { label: 'TN',       group: 'other',    pattern: '[0-9()+\\-. ]+',                                   description: 'Phone number',       example: '(123) 456-7890' },
      { label: 'ID/IS',    group: 'other',    pattern: '[A-Za-z0-9_\\-]+',                                 description: 'Alphanumeric code',  example: 'ABC, 001, CODE-1' },
    ],

    componentEditorOpen: false,
    editingComponentFieldSeq: null,
    editingComponentParentSeq: null,  // null = editing a component; number = editing a subcomponent (parent comp seq)
    componentForm: { seq: null, name: '', datatype: '', usage: 'O', repeatable: false, value_set: '' },
    compDtSearch: '',

    expandedDesc: null,
    expandedComponents: null,     // seq of field whose components sub-table is open
    expandedSubcomponents: null,  // "fieldSeq.compSeq" key for expanded subcomponent rows
    showValueSets: false,
    loadingValueSets: false,

    showValueSetModal: false,
    editingVsName: '',
    vsForm: { description: '', codes: [] },

    showDeleteProfileConfirm: false,
    showDeleteSegmentConfirm: false,
    deletingSegmentName: '',
    showDeleteFieldConfirm: false,
    deletingFieldSeq: null,
    selectedFieldSeqs: [],
    showDeleteFieldsConfirm: false,

    // ---- Global busy flag (prevents double-submits) ----
    busy: false,

    // ---- Notifications ----
    toasts: [],

    // ---- Panel resizer ----
    startResize(e, panelId) {
      e.preventDefault();
      const panel = document.getElementById(panelId);
      if (!panel) return;
      const resizer = e.target;
      resizer.classList.add('dragging');
      const startX = e.clientX;
      const startW = panel.getBoundingClientRect().width;
      const onMove = (ev) => {
        const min = parseInt(panel.style.minWidth) || 180;
        const max = parseInt(panel.style.maxWidth) || 600;
        const newW = Math.min(max, Math.max(min, startW + ev.clientX - startX));
        panel.style.width = newW + 'px';
      };
      const onUp = () => {
        resizer.classList.remove('dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    },

    // ---- Lifecycle ----
    async init() {
      await this._loadReference();
      await this.loadProfiles();
      await this.loadSharedSegments();
    },

    async _loadReference() {
      try {
        const [dt, seg, ver, uc] = await Promise.all([
          api.get('/api/reference/datatypes'),
          api.get('/api/reference/segments'),
          api.get('/api/reference/versions'),
          api.get('/api/reference/usage-codes'),
        ]);
        this.refDatatypes = dt;
        this.refSegments = seg;
        this.hl7Versions = ver;
        if (ver.includes('2.7')) this.newProfile.hl7_version = '2.7';
        this.usageCodes = uc;
      } catch (e) { this.toast('Error loading reference data: ' + e.message, 'error'); }
    },

    // ---- Profiles ----
    async loadProfiles() {
      try {
        this.profiles = await api.get('/api/profiles/');
        if (this.profiles.length > 0 && !this.selectedProfileId) {
          this.selectedProfileId = this.profiles[0].id;
          await this.loadProfile();
        }
      } catch (e) { this.toast(e.message, 'error'); }
    },

    async loadProfile() {
      if (!this.selectedProfileId) return;
      try {
        this.currentProfile = await api.get(`/api/profiles/${this.selectedProfileId}/slim`);
        this.showValueSets = false;
        this.selectedSegmentName = null;
        this._buildTree();
        const firstSeg = this.treeNodes.find(n => n.type === 'segment');
        if (firstSeg) this.selectSegment(firstSeg.segmentName);
      } catch (e) { this.toast(e.message, 'error'); }
    },

    async loadValueSets() {
      if (!this.selectedProfileId) return;
      this.loadingValueSets = true;
      try {
        const vs = await api.get(`/api/profiles/${this.selectedProfileId}/value-sets`);
        this.currentProfile = { ...this.currentProfile, value_sets: vs };
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.loadingValueSets = false; }
    },

    async createProfile() {
      if (!this.newProfile.message_type || !this.newProfile.trigger_event) {
        this.toast('Message Type and Trigger Event are required', 'error'); return;
      }
      this.busy = true;
      try {
        const p = await api.post('/api/profiles/', this.newProfile);
        this.showNewProfileModal = false;
        await this.loadProfiles();
        this.selectedProfileId = p.profile.id;
        await this.loadProfile();
        this.toast(`Profile ${p.profile.id} created`, 'success');
        this._resetNewProfileModal();
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async loadHl7stdEvents() {
      this.loadingHl7stdEvents = true;
      this.hl7stdEvents = [];
      this.hl7stdEventId = '';
      const version = this.newProfile.hl7_version;
      try {
        this.hl7stdEvents = await api.get(`/api/hl7standard/trigger-events?version=${version}`);
      } catch (e) {
        this.toast('Error loading HL7 standard events: ' + e.message, 'error');
      } finally {
        this.loadingHl7stdEvents = false;
      }
    },

    async importFromStandard() {
      if (!this.hl7stdEventId) { this.toast('Select a trigger event', 'error'); return; }
      // Close modal immediately and show full-screen progress overlay
      this.showNewProfileModal = false;
      this.importingFromStandard = true;
      this.importProgress = `Fetching HL7 ${this.newProfile.hl7_version} — ${this.hl7stdEventId} structure…`;
      const eventId = this.hl7stdEventId;
      const version = this.newProfile.hl7_version;
      try {
        this.importProgress = `Downloading segments and fields for ${eventId} (v${version})…`;
        const p = await fetch('/api/hl7standard/import', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            version,
            event_id: eventId,
            name: this.newProfile.name,
            description: this.newProfile.description,
            author: this.newProfile.author,
          }),
        });
        if (!p.ok) throw new Error((await p.json()).detail || p.statusText);
        const profile = await p.json();
        this.importProgress = 'Loading profile…';
        this._resetNewProfileModal();
        await this.loadProfiles();
        this.selectedProfileId = profile.profile.id;
        await this.loadProfile();
        this.toast(`Profile ${profile.profile.id} imported from HL7 standard`, 'success');
      } catch (e) {
        this.showNewProfileModal = false;
        this.toast(e.message, 'error');
      } finally {
        this.importingFromStandard = false;
        this.importProgress = '';
      }
    },

    _resetNewProfileModal() {
      this.newProfile = { message_type: '', trigger_event: '', hl7_version: '2.7', description: '', author: '', name: '' };
      this.importMode = 'blank';
      this.hl7stdEvents = [];
      this.hl7stdEventId = '';
      this.hl7stdEventFilter = '';
    },

    async deleteProfile() {
      this.busy = true;
      try {
        await api.delete(`/api/profiles/${this.selectedProfileId}`);
        this.showDeleteProfileConfirm = false;
        this.currentProfile = null;
        this.selectedProfileId = '';
        this.treeNodes = [];
        await this.loadProfiles();
        this.toast('Profile deleted', 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async duplicateProfile() {
      if (!this.selectedProfileId) return;
      this.busy = true;
      try {
        const p = await api.post(`/api/profiles/${this.selectedProfileId}/duplicate`, {
          name: this.duplicateName,
          message_type: this.duplicateMsgType || null,
          trigger_event: this.duplicateTrigger || null,
        });
        this.showDuplicateModal = false;
        this.duplicateName = ''; this.duplicateMsgType = ''; this.duplicateTrigger = '';
        await this.loadProfiles();
        this.selectedProfileId = p.profile.id;
        await this.loadProfile();
        this.toast(`Profile duplicated as ${p.profile.id}`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    openRenameModal() {
      if (!this.currentProfile) return;
      this.renameMsgType = this.currentProfile.profile.message_type;
      this.renameTrigger = this.currentProfile.profile.trigger_event;
      const id = this.currentProfile.profile.id;
      const base = `${this.renameMsgType}_${this.renameTrigger}`;
      this.renameName = id.startsWith(base + '_') ? id.slice(base.length + 1) : '';
      this.showRenameModal = true;
    },

    async renameProfile() {
      if (!this.selectedProfileId) return;
      this.busy = true;
      try {
        const p = await api.post(`/api/profiles/${this.selectedProfileId}/rename`, {
          name: this.renameName,
          message_type: this.renameMsgType || null,
          trigger_event: this.renameTrigger || null,
        });
        this.showRenameModal = false;
        await this.loadProfiles();
        this.selectedProfileId = p.profile.id;
        await this.loadProfile();
        this.toast(`Profile renamed to ${p.profile.id}`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    exportProfile() {
      const a = document.createElement('a');
      a.href = `/api/profiles/${this.selectedProfileId}/export`;
      a.download = `${this.selectedProfileId}.yaml`;
      a.click();
      this.toast(`Downloading ${this.selectedProfileId}.yaml…`, 'info');
    },

    async importProfile(event) {
      const file = event.target.files[0];
      if (!file) return;
      this.busy = true;
      this.toast('Importing profile…', 'info');
      const fd = new FormData();
      fd.append('file', file);
      try {
        const r = await fetch('/api/profiles/import', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const p = await r.json();
        await this.loadProfiles();
        this.selectedProfileId = p.profile.id;
        await this.loadProfile();
        this.toast(`Profile ${p.profile.id} imported`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; event.target.value = ''; }
    },

    // ---- Segment tree ----
    _buildTree() {
      this.treeNodes = [];
      this._flattenNodes(this.currentProfile.structure, 0);
    },

    _flattenNodes(nodes, depth, _counter = { n: 0 }) {
      for (const node of nodes) {
        const idx = _counter.n++;
        if (node.segment) {
          this.treeNodes.push({
            id: `seg-${node.segment}-${idx}`,
            label: node.segment,
            desc: node.description || '',
            type: 'segment',
            depth,
            segmentName: node.segment,
            usage: node.usage,
            min: node.min,
            max: node.max,
          });
        } else if (node.group) {
          this.treeNodes.push({
            id: `grp-${node.group}-${idx}`,
            label: node.group,
            desc: node.description || '',
            type: 'group',
            depth,
            usage: node.usage,
          });
          this._flattenNodes(node.segments || [], depth + 1, _counter);
        }
      }
    },

    selectSegment(segmentName) {
      this.selectedSegmentName = segmentName;
      this.selectedFieldSeqs = [];
      this.expandedDesc = null;
      this.expandedComponents = null;
      this.expandedSubcomponents = null;
    },

    // ---- Segment CRUD ----
    openAddSegmentModal() {
      this.newSegment = { segment: '', usage: 'O', min: 0, max: 1, description: '' };
      this.segmentSearch = '';
      this.showSegmentModal = true;
    },

    selectSegmentFromList(code) {
      this.newSegment.segment = code;
      const ref = this.refSegments.find(s => s.code === code);
      if (ref && !this.newSegment.description) this.newSegment.description = ref.name;
    },

    async addSegment() {
      if (!this.newSegment.segment) { this.toast('Select a segment', 'error'); return; }
      this.busy = true;
      const payload = { ...this.newSegment, max: this.newSegment.max === '*' ? '*' : Number(this.newSegment.max) };
      try {
        this.currentProfile = await api.post(`/api/profiles/${this.selectedProfileId}/segments`, payload);
        this._buildTree();
        this.selectSegment(this.newSegment.segment);
        this.showSegmentModal = false;
        this.toast(`Segment ${this.newSegment.segment} added`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    // ---- Shared segment library ----
    async loadSharedSegments() {
      try { this.sharedSegments = await api.get('/api/shared-segments/'); }
      catch (e) { this.toast(e.message, 'error'); }
    },

    openSaveSharedModal() {
      if (!this.selectedSegment) return;
      this.saveSharedId = this.selectedSegment.segment;
      this.saveSharedDesc = '';
      this.showSaveSharedModal = true;
    },

    async saveAsShared() {
      if (!this.saveSharedId.trim()) { this.toast('Name is required', 'error'); return; }
      this.busy = true;
      try {
        await api.post(
          `/api/shared-segments/from-profile/${this.selectedProfileId}/segments/${this.selectedSegmentName}`,
          { shared_id: this.saveSharedId.trim(), description: this.saveSharedDesc || null }
        );
        await this.loadSharedSegments();
        this.showSaveSharedModal = false;
        this.toast(`Saved as shared: ${this.saveSharedId.trim()}`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async applySharedSegment(sharedId) {
      if (!this.selectedProfileId) return;
      this.busy = true;
      try {
        this.currentProfile = await api.post('/api/shared-segments/apply-to-profile/' + this.selectedProfileId, { shared_id: sharedId });
        this._buildTree();
        this.showSegmentModal = false;
        this.toast(`Segment ${sharedId} applied`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async deleteSharedSegment(sharedId) {
      if (!confirm(`Delete shared segment "${sharedId}"?`)) return;
      try {
        await api.delete(`/api/shared-segments/${sharedId}`);
        this.sharedSegments = this.sharedSegments.filter(s => s.id !== sharedId);
        this.toast(`Shared segment ${sharedId} deleted`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
    },

    openEditSegmentModal() {
      const seg = this.selectedSegment;
      if (!seg) return;
      this.editSegment = { segment: seg.segment, usage: seg.usage, min: seg.min, max: seg.max, description: seg.description || '' };
      this.showEditSegmentModal = true;
    },

    async saveEditSegment() {
      this.busy = true;
      const payload = { ...this.editSegment, max: this.editSegment.max === '*' ? '*' : Number(this.editSegment.max) };
      try {
        this.currentProfile = await api.put(`/api/profiles/${this.selectedProfileId}/segments/${this.editSegment.segment}`, payload);
        this._buildTree();
        this.selectSegment(this.editSegment.segment);
        this.showEditSegmentModal = false;
        this.toast(`Segment ${this.editSegment.segment} updated`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    confirmDeleteSegment(segmentName) {
      this.deletingSegmentName = segmentName;
      this.showDeleteSegmentConfirm = true;
    },

    async deleteSegment() {
      this.busy = true;
      try {
        this.currentProfile = await api.delete(`/api/profiles/${this.selectedProfileId}/segments/${this.deletingSegmentName}`);
        this._buildTree();
        if (this.selectedSegmentName === this.deletingSegmentName) this.selectedSegmentName = null;
        this.showDeleteSegmentConfirm = false;
        this.toast(`Segment ${this.deletingSegmentName} removed`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async moveSegment(segmentName, direction) {
      try {
        this.currentProfile = await api.post(
          `/api/profiles/${this.selectedProfileId}/segments/${segmentName}/move`,
          { direction }
        );
        this._buildTree();
      } catch (e) { this.toast(e.message, 'error'); }
    },

    // ---- Field CRUD ----
    async openFieldEditor(field) {
      if (!Object.keys(this.profileValueSets).length) await this.loadValueSets();
      if (field) {
        const pattern = field.format_pattern || '';
        const preset = this.formatPresets.find(p => p.pattern === pattern);
        this.fieldForm = {
          ...field,
          value_set: field.value_set || '',
          format_pattern: pattern,
          format_preset: preset ? preset.label : (pattern ? '__custom__' : ''),
        };
      } else {
        this.fieldForm = { seq: null, name: '', datatype: 'ST', usage: 'O', repeatable: false, min_length: 0, max_length: 999, description: '', notes: '', value_set: '', format_pattern: '', format_preset: '' };
      }
      this.editingField = field;
      this.dtSearch = '';
      this.fieldEditorOpen = true;
    },

    onFormatPresetChange() {
      const preset = this.formatPresets.find(p => p.label === this.fieldForm.format_preset);
      if (preset) {
        this.fieldForm.format_pattern = preset.pattern;
      } else if (this.fieldForm.format_preset === '') {
        this.fieldForm.format_pattern = '';
      }
      // '__custom__' → keep format_pattern as-is for user to edit
    },

    get filteredDatatypes() {
      const q = this.dtSearch.toLowerCase();
      if (!q) return this.refDatatypes;
      return this.refDatatypes.filter(d => d.code.toLowerCase().includes(q) || d.name.toLowerCase().includes(q));
    },

    get filteredCompDatatypes() {
      const q = this.compDtSearch.toLowerCase();
      if (!q) return this.refDatatypes;
      return this.refDatatypes.filter(d => d.code.toLowerCase().includes(q) || d.name.toLowerCase().includes(q));
    },

    setUsageOnField(code) { this.fieldForm.usage = code; },

    async saveField() {
      if (!this.fieldForm.seq || !this.fieldForm.name || !this.fieldForm.datatype) {
        this.toast('Seq, Name and Datatype are required', 'error'); return;
      }
      this.busy = true;
      const { format_preset, ...rest } = this.fieldForm;
      const payload = { ...rest, value_set: rest.value_set || null, format_pattern: rest.format_pattern || null };
      try {
        this.currentProfile = await api.post(
          `/api/profiles/${this.selectedProfileId}/segments/${this.selectedSegmentName}/fields`,
          payload
        );
        this._buildTree();
        this.fieldEditorOpen = false;
        this.toast(`Field ${this.selectedSegmentName}.${this.fieldForm.seq} saved`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    // ---- Component editor ----
    async openComponentEditor(field, comp, parentComp = null) {
      if (!Object.keys(this.profileValueSets).length) await this.loadValueSets();
      this.editingComponentFieldSeq = field.seq;
      this.editingComponentParentSeq = parentComp ? parentComp.seq : null;
      this.componentForm = { ...comp, value_set: comp.value_set || '' };
      this.compDtSearch = '';
      this.componentEditorOpen = true;
    },

    async saveComponent() {
      this.busy = true;
      const seg = this._findSegment(this.currentProfile.structure, this.selectedSegmentName);
      if (!seg) { this.busy = false; return; }
      const field = seg.fields.find(f => f.seq === this.editingComponentFieldSeq);
      if (!field) return;

      if (this.editingComponentParentSeq !== null) {
        // Editing a subcomponent — navigate to parent component first
        const parentComp = field.components.find(c => c.seq === this.editingComponentParentSeq);
        if (!parentComp) return;
        const idx = parentComp.components.findIndex(s => s.seq === this.componentForm.seq);
        if (idx === -1) return;
        parentComp.components[idx] = {
          ...parentComp.components[idx],
          name: this.componentForm.name,
          datatype: this.componentForm.datatype,
          usage: this.componentForm.usage,
          repeatable: this.componentForm.repeatable,
          value_set: this.componentForm.value_set || null,
        };
      } else {
        // Editing a component
        const idx = field.components.findIndex(c => c.seq === this.componentForm.seq);
        if (idx === -1) return;
        field.components[idx] = {
          ...field.components[idx],
          name: this.componentForm.name,
          datatype: this.componentForm.datatype,
          usage: this.componentForm.usage,
          repeatable: this.componentForm.repeatable,
          value_set: this.componentForm.value_set || null,
        };
      }

      // Persist via full field upsert (components + subcomponents included)
      const payload = { ...field, value_set: field.value_set || null };
      try {
        this.currentProfile = await api.post(
          `/api/profiles/${this.selectedProfileId}/segments/${this.selectedSegmentName}/fields`,
          payload
        );
        this._buildTree();
        this.componentEditorOpen = false;
        const loc = this.editingComponentParentSeq !== null
          ? `${this.selectedSegmentName}.${this.editingComponentFieldSeq}.${this.editingComponentParentSeq}.${this.componentForm.seq}`
          : `${this.selectedSegmentName}.${this.editingComponentFieldSeq}.${this.componentForm.seq}`;
        this.toast(`Saved ${loc}`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    _findSegment(nodes, name) {
      for (const node of nodes) {
        if (node.segment === name) return node;
        if (node.segments) { const r = this._findSegment(node.segments, name); if (r) return r; }
      }
      return null;
    },

    confirmDeleteField(seq) {
      this.deletingFieldSeq = seq;
      this.showDeleteFieldConfirm = true;
    },

    async deleteField() {
      this.busy = true;
      try {
        this.currentProfile = await api.delete(
          `/api/profiles/${this.selectedProfileId}/segments/${this.selectedSegmentName}/fields/${this.deletingFieldSeq}`
        );
        this._buildTree();
        this.showDeleteFieldConfirm = false;
        this.toast(`Field seq=${this.deletingFieldSeq} deleted`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    toggleFieldSelection(seq) {
      const idx = this.selectedFieldSeqs.indexOf(seq);
      if (idx === -1) this.selectedFieldSeqs.push(seq);
      else this.selectedFieldSeqs.splice(idx, 1);
    },

    toggleAllFields() {
      const all = this.selectedSegmentFields.map(f => f.seq);
      if (this.selectedFieldSeqs.length === all.length) this.selectedFieldSeqs = [];
      else this.selectedFieldSeqs = [...all];
    },

    async deleteSelectedFields() {
      this.busy = true;
      const seqs = [...this.selectedFieldSeqs];
      for (const seq of seqs) {
        try {
          this.currentProfile = await api.delete(
            `/api/profiles/${this.selectedProfileId}/segments/${this.selectedSegmentName}/fields/${seq}`
          );
        } catch (e) { this.toast(`Error deleting field ${seq}: ${e.message}`, 'error'); }
      }
      this._buildTree();
      this.selectedFieldSeqs = [];
      this.showDeleteFieldsConfirm = false;
      this.busy = false;
      this.toast(`${seqs.length} field(s) deleted`, 'success');
    },

    // ---- Value Sets ----
    get profileValueSets() {
      if (!this.currentProfile) return {};
      return this.currentProfile.value_sets || {};
    },

    get valueSetsGroupedBySegment() {
      if (!this.currentProfile) return [];
      const vs = this.currentProfile.value_sets || {};
      const groups = {};
      const fieldIndex = {};
      const walk = (nodes) => {
        for (const node of nodes) {
          if (node.segment) {
            for (const f of node.fields || []) {
              if (f.value_set) fieldIndex[f.value_set] = { seg: node.segment, seq: f.seq, name: f.name };
            }
          } else if (node.group) { walk(node.segments || []); }
        }
      };
      walk(this.currentProfile.structure || []);
      const ungrouped = [];
      for (const [vsName, vsData] of Object.entries(vs)) {
        const info = fieldIndex[vsName];
        if (info) {
          if (!groups[info.seg]) groups[info.seg] = [];
          groups[info.seg].push({ vsName, fieldSeq: info.seq, fieldName: info.name, vs: vsData });
        } else { ungrouped.push({ vsName, vs: vsData }); }
      }
      for (const seg of Object.keys(groups)) groups[seg].sort((a, b) => a.fieldSeq - b.fieldSeq);
      const result = Object.entries(groups).sort(([a],[b]) => a.localeCompare(b))
        .map(([seg, items]) => ({ seg, items }));
      if (ungrouped.length) result.push({ seg: null, items: ungrouped });
      return result;
    },

    async openValueSetEditor(vsName) {
      if (vsName && !this.profileValueSets[vsName]) {
        await this.loadValueSets();
      }
      this.editingVsName = vsName || '';
      if (vsName && this.profileValueSets[vsName]) {
        const vs = this.profileValueSets[vsName];
        this.vsForm = {
          description: vs.description || '',
          codes: vs.codes ? vs.codes.map(c => ({ ...c })) : [],
          newName: vsName,
        };
      } else {
        this.vsForm = { description: '', codes: [], newName: '' };
      }
      this.showValueSetModal = true;
    },

    addVsCode() {
      this.vsForm.codes.push({ code: '', display: '', description: '' });
    },

    removeVsCode(idx) {
      this.vsForm.codes.splice(idx, 1);
    },

    async saveValueSet() {
      const name = this.vsForm.newName || this.editingVsName;
      if (!name) { this.toast('Value set name is required', 'error'); return; }
      this.busy = true;
      const payload = { description: this.vsForm.description, codes: this.vsForm.codes };
      try {
        this.currentProfile = await api.post(`/api/profiles/${this.selectedProfileId}/value-sets/${name}`, payload);
        this.showValueSetModal = false;
        this.toast(`Value set ${name} saved`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    async deleteValueSet(vsName) {
      if (!confirm(`Delete value set "${vsName}"?`)) return;
      this.busy = true;
      try {
        this.currentProfile = await api.delete(`/api/profiles/${this.selectedProfileId}/value-sets/${vsName}`);
        this.toast(`Value set ${vsName} deleted`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    // ---- Helpers ----
    _findSegment(nodes, name) {
      for (const node of nodes) {
        if (node.segment === name) return node;
        if (node.group && node.segments) {
          const found = this._findSegment(node.segments, name);
          if (found) return found;
        }
      }
      return null;
    },

    usageLabel(code) {
      const uc = this.usageCodes.find(u => u.code === code);
      return uc ? uc.name : code;
    },

    datatypeName(code) {
      const dt = this.refDatatypes.find(d => d.code === code);
      return dt ? dt.name : code;
    },

    // ---- Toast notifications ----
    toast(msg, type = 'info') {
      const id = Date.now();
      this.toasts.push({ id, msg, type });
      setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 4000);
    },

    toastBg(type) {
      return { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-blue-600' }[type] || 'bg-gray-700';
    },

    // ---- Tab navigation ----
    activeTab: 'editor',   // 'editor' | 'validator'

    // ---- Validator state ----
    validatorProfileId: '',
    validatorMessage: '',
    validationResult: null,
    validating: false,

    get validatorProfiles() { return this.profiles; },

    get validationBySegment() {
      if (!this.validationResult) return [];
      const allIssues = [...this.validationResult.errors, ...this.validationResult.warnings];
      // group by segment
      const map = {};
      for (const issue of allIssues) {
        if (!map[issue.segment]) map[issue.segment] = [];
        map[issue.segment].push(issue);
      }
      return Object.entries(map).map(([seg, issues]) => ({ seg, issues }));
    },

    async runValidation() {
      if (!this.validatorProfileId) { this.toast('Select a profile first', 'error'); return; }
      if (!this.validatorMessage.trim()) { this.toast('Paste an HL7 message first', 'error'); return; }
      this.validating = true;
      this.validationResult = null;
      try {
        this.validationResult = await api.post('/api/validate/', {
          profile_id: this.validatorProfileId,
          message: this.validatorMessage,
        });
      } catch (e) {
        this.toast(e.message, 'error');
      } finally {
        this.validating = false;
      }
    },

    clearValidator() {
      this.validatorMessage = '';
      this.validationResult = null;
    },

    // ---- Backup / Restore ----
    showMenu: false,

    backupDownload() {
      const a = document.createElement('a');
      a.href = '/api/backup/';
      a.download = `hl7-backup-${new Date().toISOString().slice(0, 10)}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      this.toast('Downloading backup…', 'info');
    },

    async restoreBackup(file) {
      if (!file) return;
      this.busy = true;
      this.toast('Restoring backup…', 'info');
      const fd = new FormData();
      fd.append('file', file);
      try {
        const r = await fetch('/api/backup/restore', { method: 'POST', body: fd });
        if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
        const data = await r.json();
        await this.loadProfiles();
        this.toast(`Backup restored — ${data.profiles_restored} profile(s)`, 'success');
      } catch (e) { this.toast(e.message, 'error'); }
      finally { this.busy = false; }
    },

    exportReportPdf() {
      const r = this.validationResult;
      if (!r) return;

      // Build a set of "field" references that have issues for quick lookup
      const errorFields  = new Set(r.errors.map(e => e.field));
      const warnFields   = new Set(r.warnings.map(w => w.field));
      const errorSegs    = new Set(r.errors.map(e => e.segment));
      const warnSegs     = new Set(r.warnings.map(w => w.segment));

      // ---- helpers ----
      const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

      // Highlight individual fields inside a segment line
      // seg = "PID", fields = ["PID","1","","MRN123^^..."], issues on field refs like "PID.3"
      const highlightSeg = (segName, rawLine) => {
        const parts = rawLine.split('|');
        const highlighted = parts.map((val, idx) => {
          const fieldRef = idx === 0 ? segName : `${segName}.${segName === 'MSH' ? idx : idx}`;
          const hasErr  = errorFields.has(fieldRef);
          const hasWarn = warnFields.has(fieldRef);
          const escaped = esc(val);
          if (hasErr)  return `<span class="hl-error">${escaped}</span>`;
          if (hasWarn) return `<span class="hl-warn">${escaped}</span>`;
          return escaped;
        });
        return highlighted.join('<span class="pipe">|</span>');
      };

      // Render message section with per-segment and per-field highlighting
      const msgLines = this.validatorMessage.trim().split(/\r?\n/).filter(l => l.trim());
      const msgHtml = msgLines.map(line => {
        const segName = line.split('|')[0];
        const hasErr  = errorSegs.has(segName);
        const hasWarn = warnSegs.has(segName);
        const cls = hasErr ? 'seg-error' : hasWarn ? 'seg-warn' : 'seg-ok';
        return `<div class="seg-line ${cls}">${highlightSeg(segName, line)}</div>`;
      }).join('');

      // Render issues grouped by segment
      const allIssues = [...r.errors, ...r.warnings].sort((a,b) => a.segment.localeCompare(b.segment) || a.seq - b.seq);
      const bySegMap = {};
      allIssues.forEach(i => { (bySegMap[i.segment] = bySegMap[i.segment] || []).push(i); });
      const issuesHtml = Object.entries(bySegMap).map(([seg, issues]) => `
        <div class="issue-group">
          <div class="issue-seg-header">${esc(seg)}</div>
          ${issues.map(i => `
            <div class="issue-row ${i.severity === 'ERROR' ? 'issue-error' : 'issue-warn'}">
              <span class="issue-badge">${esc(i.severity)}</span>
              <span class="issue-field">${esc(i.seq > 0 ? i.field : i.segment)}</span>
              <span class="issue-rule">${esc(i.rule)}</span>
              <span class="issue-msg">${esc(i.message)}</span>
              ${i.value ? `<span class="issue-val">Value: <code>${esc(i.value)}</code></span>` : ''}
            </div>`).join('')}
        </div>`).join('');

      const now = new Date().toLocaleString();
      const statusColor = r.is_valid ? '#16a34a' : '#dc2626';
      const statusText  = r.is_valid ? 'VALID' : `INVALID — ${r.error_count} error(s)`;

      const html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Validation Report — ${esc(r.profile_id)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 12px; color: #1f2937; padding: 32px; }
  @media print { body { padding: 16px; } }
  h1 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
  .meta { color: #6b7280; font-size: 11px; margin-bottom: 20px; }
  .status { display: inline-block; padding: 4px 12px; border-radius: 6px; font-weight: 700;
            font-size: 13px; color: white; background: ${statusColor}; margin-bottom: 20px; }
  .summary-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 24px; }
  .summary-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; }
  .summary-card .label { font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: .05em; }
  .summary-card .value { font-size: 14px; font-weight: 600; margin-top: 2px; }
  h2 { font-size: 13px; font-weight: 700; border-bottom: 2px solid #e5e7eb;
       padding-bottom: 4px; margin: 20px 0 10px; text-transform: uppercase; letter-spacing: .05em; color: #374151; }
  .msg-block { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
               padding: 12px 16px; font-family: 'Courier New', monospace; font-size: 11px; line-height: 1.8; }
  .seg-line { margin-bottom: 2px; }
  .seg-error { background: #fef2f2; border-left: 3px solid #ef4444; padding-left: 6px; border-radius: 2px; }
  .seg-warn  { background: #fffbeb; border-left: 3px solid #f59e0b; padding-left: 6px; border-radius: 2px; }
  .seg-ok    { padding-left: 9px; }
  .pipe { color: #9ca3af; }
  .hl-error { background: #fee2e2; color: #991b1b; border-radius: 2px; padding: 0 2px; font-weight: 600; }
  .hl-warn  { background: #fef3c7; color: #92400e; border-radius: 2px; padding: 0 2px; font-weight: 600; }
  .issue-group { margin-bottom: 12px; }
  .issue-seg-header { font-family: monospace; font-weight: 700; font-size: 12px;
                      background: #f3f4f6; padding: 4px 10px; border-radius: 4px; margin-bottom: 4px; }
  .issue-row { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px;
               padding: 5px 10px; border-radius: 4px; margin-bottom: 3px; font-size: 11px; }
  .issue-error { background: #fef2f2; border-left: 3px solid #ef4444; }
  .issue-warn  { background: #fffbeb; border-left: 3px solid #f59e0b; }
  .issue-badge { font-weight: 700; font-size: 10px; padding: 1px 6px; border-radius: 3px;
                 color: white; flex-shrink: 0; }
  .issue-error .issue-badge { background: #ef4444; }
  .issue-warn  .issue-badge { background: #f59e0b; }
  .issue-field { font-family: monospace; font-weight: 600; color: #1d4ed8; }
  .issue-rule  { font-family: monospace; font-size: 10px; color: #6b7280;
                 background: #f3f4f6; padding: 1px 5px; border-radius: 3px; }
  .issue-msg   { flex: 1; color: #374151; }
  .issue-val   { width: 100%; margin-top: 2px; color: #9ca3af; }
  .issue-val code { background: #f3f4f6; padding: 0 4px; border-radius: 3px; color: #374151; }
  .footer { margin-top: 32px; font-size: 10px; color: #d1d5db; border-top: 1px solid #f3f4f6; padding-top: 8px; }
  .legend { display: flex; gap: 16px; margin-bottom: 8px; font-size: 10px; }
  .legend-item { display: flex; align-items: center; gap: 4px; }
  .legend-dot { width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }
</style>
</head>
<body>
  <h1>HL7 Validation Report</h1>
  <div class="meta">Generated: ${now}</div>

  <div class="status">${statusText}</div>

  <div class="summary-grid">
    <div class="summary-card">
      <div class="label">Profile</div>
      <div class="value" style="font-size:11px;font-family:monospace">${esc(r.profile_id)}</div>
    </div>
    <div class="summary-card">
      <div class="label">HL7 Version</div>
      <div class="value">${esc(r.hl7_version)}</div>
    </div>
    <div class="summary-card">
      <div class="label">Message Type</div>
      <div class="value" style="font-family:monospace">${esc(r.message_type) || '—'}</div>
    </div>
    <div class="summary-card">
      <div class="label">Errors</div>
      <div class="value" style="color:${r.error_count > 0 ? '#dc2626' : '#16a34a'}">${r.error_count}</div>
    </div>
    <div class="summary-card">
      <div class="label">Warnings</div>
      <div class="value" style="color:${r.warning_count > 0 ? '#d97706' : '#16a34a'}">${r.warning_count}</div>
    </div>
    <div class="summary-card">
      <div class="label">Segments found</div>
      <div class="value" style="font-size:10px;font-family:monospace">${esc(r.segments_found.join(' · '))}</div>
    </div>
  </div>

  <h2>Original Message</h2>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#fee2e2;border-left:3px solid #ef4444"></div> Error</div>
    <div class="legend-item"><div class="legend-dot" style="background:#fef3c7;border-left:3px solid #f59e0b"></div> Warning</div>
  </div>
  <div class="msg-block">${msgHtml}</div>

  ${allIssues.length > 0 ? `<h2>Issues Detail</h2>${issuesHtml}` : '<h2>Issues Detail</h2><p style="color:#16a34a;margin-top:8px">No issues found. All profile rules passed.</p>'}

  <div class="footer">HL7 Profile Validator &nbsp;·&nbsp; ${esc(r.profile_id)} &nbsp;·&nbsp; ${now}</div>
</body>
</html>`;

      const blob = new Blob([html], { type: 'text/html' });
      const url  = URL.createObjectURL(blob);
      const win  = window.open(url, '_blank');
      win.addEventListener('load', () => { win.focus(); win.print(); });
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    },

    loadSampleMessage() {
      const p = this.profiles.find(x => x.id === this.validatorProfileId);
      if (!p) return;
      const now = new Date().toISOString().replace(/[-T:.Z]/g, '').slice(0, 14);
      const msgCtrl = 'MSG' + Date.now();

      // Build PV1 with correct field positions (45 items: index 0=PV1, 1..44=fields)
      const pv1fields = new Array(45).fill('');
      pv1fields[0]  = 'PV1';
      pv1fields[1]  = '1';
      pv1fields[2]  = 'O';          // PV1.2 Patient Class
      pv1fields[3]  = 'CLINIC^^^HOSPITAL';  // PV1.3 Location
      pv1fields[7]  = 'DR001^SMITH^JOHN^^^DR'; // PV1.7 Attending Doctor
      pv1fields[19] = 'VISIT001^^^HOSPITAL';   // PV1.19 Visit Number
      pv1fields[44] = now;                     // PV1.44 Admit Date/Time

      this.validatorMessage = [
        `MSH|^~\\&|SENDING_APP|HOSPITAL|RECEIVING_APP|HOSPITAL|${now}||${p.message_type}^${p.trigger_event}^${p.message_type}_A01|${msgCtrl}|P|${p.hl7_version}`,
        `EVN||${now}`,
        `PID|1||MRN001^^^HOSPITAL^MR||DOE^JOHN^A||19800101|M|||123 MAIN ST^^CITY^ST^12345`,
        pv1fields.join('|'),
      ].join('\r');
    },

    ruleBadge(rule) {
      const map = {
        SEGMENT_REQUIRED:      { label: 'Required', color: 'bg-red-100 text-red-700' },
        SEGMENT_NOT_SUPPORTED: { label: 'Not Supported', color: 'bg-red-100 text-red-700' },
        SEGMENT_CARDINALITY:   { label: 'Cardinality', color: 'bg-orange-100 text-orange-700' },
        FIELD_REQUIRED:        { label: 'Required', color: 'bg-red-100 text-red-700' },
        FIELD_NOT_SUPPORTED:   { label: 'Not Supported', color: 'bg-red-100 text-red-700' },
        FIELD_MAX_LENGTH:      { label: 'Max Length', color: 'bg-orange-100 text-orange-700' },
        INVALID_CODE:          { label: 'Invalid Code', color: 'bg-yellow-100 text-yellow-700' },
      };
      return map[rule] || { label: rule, color: 'bg-gray-100 text-gray-600' };
    },
  };
}
