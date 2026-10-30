import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CalendarDays, CheckCircle2, ChevronRight, ClipboardList, LayoutDashboard, LoaderCircle, Menu, Plus, RefreshCw, Users, X } from 'lucide-react'
import { apiRequest } from './services/api'

const statuses = ['Open', 'In Progress', 'Blocked', 'Completed']
const today = new Date().toISOString().slice(0, 10)
const date = (value) => value ? new Intl.DateTimeFormat('en', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(`${value}T12:00:00`)) : 'No date'
const overdue = (task) => task.status !== 'Completed' && task.due_date && task.due_date < today
const Status = ({ value }) => <span className={`status ${value.toLowerCase().replaceAll(' ', '-')}`}>{value}</span>

export default function App() {
  const [view, setView] = useState('dashboard')
  const [meetings, setMeetings] = useState([])
  const [tasks, setTasks] = useState([])
  const [selected, setSelected] = useState(null)
  const [filter, setFilter] = useState('All')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [menu, setMenu] = useState(false)

  const load = async () => {
    setLoading(true); setError('')
    try {
      const [meetingData, taskData] = await Promise.all([apiRequest('/api/meetings'), apiRequest('/api/tasks')])
      setMeetings(meetingData); setTasks(taskData)
    } catch (err) { setError(err.message || 'Unable to load the workspace.') } finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])
  const show = (next) => { setView(next); setMenu(false); setNotice('') }
  const metrics = useMemo(() => ({ meetings: meetings.length, open: tasks.filter((task) => task.status !== 'Completed').length, overdue: tasks.filter(overdue).length, completed: tasks.filter((task) => task.status === 'Completed').length }), [meetings, tasks])

  const saveMeeting = async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget)
    const payload = { title: form.get('title'), meeting_type: form.get('meeting_type'), meeting_date: form.get('meeting_date'), agenda: form.get('agenda'), participants: form.get('participants').split(',').map((person) => person.trim()).filter(Boolean), raw_notes: form.get('raw_notes') }
    setSaving(true); setError('')
    try { const item = await apiRequest('/api/meetings', { method: 'POST', body: JSON.stringify(payload) }); setMeetings((items) => [item, ...items]); setSelected(item); event.currentTarget.reset(); setNotice('Meeting saved. You can now link work to it.') } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const saveTask = async (event) => {
    event.preventDefault(); const form = new FormData(event.currentTarget); const meetingId = form.get('origin_meeting_id')
    const payload = { title: form.get('title'), description: form.get('description') || null, owner: form.get('owner') || null, due_date: form.get('due_date') || null, origin_meeting_id: meetingId ? Number(meetingId) : null }
    setSaving(true); setError('')
    try { const item = await apiRequest('/api/tasks', { method: 'POST', body: JSON.stringify(payload) }); setTasks((items) => [item, ...items]); event.currentTarget.reset(); setNotice('Task created and added to the workflow.') } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const patchTask = async (id, changes) => {
    try { const item = await apiRequest(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(changes) }); setTasks((items) => items.map((task) => task.id === id ? item : task)) } catch (err) { setError(err.message || 'Unable to update the task.') }
  }
  const carryTask = async (id, meetingId) => {
    try { await apiRequest(`/api/tasks/${id}/carry-forward`, { method: 'POST', body: JSON.stringify({ meeting_id: Number(meetingId) }) }); setNotice('Task carried forward to the selected meeting.') } catch (err) { setError(err.message || 'Unable to carry the task forward.') }
  }
  const analyzeMeeting = async () => {
    if (!selected) return
    setSaving(true); setError('')
    try {
      const result = await apiRequest('/api/ai/process-notes', { method: 'POST', body: JSON.stringify({ raw_notes: selected.raw_notes, meeting_date: selected.meeting_date, participants: selected.participants }) })
      setAnalysis(result)
    } catch (err) { setError(err.message || 'AI analysis could not be generated.') } finally { setSaving(false) }
  }
  const approveAnalysis = async () => {
    if (!selected || !analysis) return
    setSaving(true); setError('')
    try {
      const meeting = await apiRequest(`/api/meetings/${selected.id}`, { method: 'PATCH', body: JSON.stringify({ summary: analysis.summary, decisions: analysis.decisions.map((decision) => `• ${decision}`).join('\n') || null }) })
      const created = await Promise.all(analysis.action_items.map((item) => apiRequest('/api/tasks', { method: 'POST', body: JSON.stringify({ title: item.title, description: item.description, owner: item.owner, due_date: item.due_date, origin_meeting_id: selected.id }) })))
      setMeetings((items) => items.map((item) => item.id === meeting.id ? meeting : item)); setSelected(meeting); setTasks((items) => [...created, ...items]); setAnalysis(null); setNotice('AI analysis approved and saved.')
    } catch (err) { setError(err.message || 'Unable to save the approved analysis.') } finally { setSaving(false) }
  }
  const visibleTasks = filter === 'All' ? tasks : tasks.filter((task) => task.status === filter)

  return <div className="workspace">
    <aside className={menu ? 'sidebar open' : 'sidebar'}><div className="brand"><b>D</b> Digi<span>Plus</span><button className="close" onClick={() => setMenu(false)}><X size={19} /></button></div><nav><Nav icon={<LayoutDashboard />} label="Dashboard" active={view === 'dashboard'} onClick={() => show('dashboard')} /><Nav icon={<CalendarDays />} label="Meetings" active={view === 'meetings'} onClick={() => show('meetings')} /><Nav icon={<ClipboardList />} label="Tasks" active={view === 'tasks'} onClick={() => show('tasks')} /><Nav icon={<Users />} label="Knowledge" soon /><Nav icon={<ChevronRight />} label="Smart Handover" soon /></nav><div className="workspace-label">DIGIPLUS WORKSPACE<br /><small>Project command center</small></div></aside>
    <main><header><button className="mobile-menu" onClick={() => setMenu(true)}><Menu size={22} /></button><div><p className="eyebrow">WORKSPACE OVERVIEW</p><h1>{view === 'dashboard' ? 'Good morning, team.' : view[0].toUpperCase() + view.slice(1)}</h1></div><button className="refresh" onClick={load} aria-label="Refresh"><RefreshCw className={loading ? 'spin' : ''} size={18} /></button></header>
      {error && <Message type="error" text={error} onClose={() => setError('')} />}{notice && <Message type="success" text={notice} onClose={() => setNotice('')} />}
      {loading ? <div className="loading"><LoaderCircle className="spin" /> Loading your workspace…</div> : view === 'dashboard' ? <Dashboard metrics={metrics} meetings={meetings} tasks={tasks} onShow={show} onMeeting={(meeting) => { setSelected(meeting); show('meetings') }} /> : view === 'meetings' ? <Meetings meetings={meetings} selected={selected} onSelect={setSelected} onSave={saveMeeting} saving={saving} analysis={analysis} onAnalyze={analyzeMeeting} onApprove={approveAnalysis} onDiscard={() => setAnalysis(null)} /> : <Tasks meetings={meetings} tasks={visibleTasks} filter={filter} onFilter={setFilter} onSave={saveTask} onPatch={patchTask} onCarry={carryTask} saving={saving} />}
    </main>
  </div>
}

function Nav({ icon, label, active, onClick, soon }) { return <button className={`nav ${active ? 'active' : ''} ${soon ? 'soon' : ''}`} onClick={onClick} disabled={soon}>{icon}{label}{soon && <small>Soon</small>}</button> }
function Message({ type, text, onClose }) { return <div className={`message ${type}`}><AlertCircle size={18} /><span>{text}</span><button onClick={onClose}><X size={17} /></button></div> }
function Metric({ label, value, tone, icon }) { return <article className={`metric ${tone}`}><span>{icon}</span><div><strong>{value}</strong><small>{label}</small></div></article> }
function Empty({ label, action }) { return <div className="empty"><ClipboardList size={25} /><p>{label}</p>{action}</div> }

function Dashboard({ metrics, meetings, tasks, onShow, onMeeting }) {
  const upcoming = tasks.filter((task) => task.status !== 'Completed').slice(0, 5)
  return <><section className="metrics"><Metric label="Total meetings" value={metrics.meetings} tone="purple" icon={<CalendarDays />} /><Metric label="Open tasks" value={metrics.open} tone="blue" icon={<ClipboardList />} /><Metric label="Overdue" value={metrics.overdue} tone="red" icon={<AlertCircle />} /><Metric label="Completed" value={metrics.completed} tone="green" icon={<CheckCircle2 />} /></section><section className="action-banner"><div><p className="eyebrow">MOVE WORK FORWARD</p><h2>What needs your attention?</h2></div><div><button className="light-button" onClick={() => onShow('meetings')}><Plus size={17} /> New meeting</button><button className="light-button" onClick={() => onShow('tasks')}><Plus size={17} /> New task</button></div></section><section className="panels"><article className="panel"><PanelTitle eyebrow="RECENT CONTEXT" title="Recent meetings" button="View all" onClick={() => onShow('meetings')} />{meetings.length ? <div className="list">{meetings.slice(0, 4).map((meeting) => <button className="meeting-row" key={meeting.id} onClick={() => onMeeting(meeting)}><DateTile value={meeting.meeting_date} /><span><strong>{meeting.title}</strong><small>{meeting.meeting_type} · {meeting.participants.length} participants</small></span><ChevronRight size={17} /></button>)}</div> : <Empty label="No meetings saved yet." action={<button className="link" onClick={() => onShow('meetings')}>Create your first meeting</button>} />}</article><article className="panel"><PanelTitle eyebrow="STAY ON TRACK" title="Upcoming deadlines" button="View all" onClick={() => onShow('tasks')} />{upcoming.length ? <div className="list">{upcoming.map((task) => <div className="deadline" key={task.id}><i className={overdue(task) ? 'late' : ''} /><span><strong>{task.title}</strong><small>{task.owner || 'Unassigned'} · {date(task.due_date)}</small></span><Status value={task.status} /></div>)}</div> : <Empty label="No open tasks right now." action={<button className="link" onClick={() => onShow('tasks')}>Add a task</button>} />}</article></section></>
}
function PanelTitle({ eyebrow, title, button, onClick }) { return <div className="panel-title"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{button && <button className="link" onClick={onClick}>{button} <ChevronRight size={16} /></button>}</div> }
function DateTile({ value }) { const item = new Date(`${value}T12:00:00`); return <span className="date-tile"><b>{item.getDate()}</b><small>{new Intl.DateTimeFormat('en', { month: 'short' }).format(item)}</small></span> }

function Meetings({ meetings, selected, onSelect, onSave, saving, analysis, onAnalyze, onApprove, onDiscard }) {
  return <section className="content-grid meetings"><article className="panel"><PanelTitle eyebrow="CAPTURE CONTEXT" title="New meeting" /><form className="form" onSubmit={onSave}><label>Title<input name="title" required placeholder="Weekly delivery sync" /></label><div className="split"><label>Type<input name="meeting_type" required defaultValue="Meeting" /></label><label>Date<input name="meeting_date" type="date" defaultValue={today} required /></label></div><label>Agenda<textarea name="agenda" required rows="2" placeholder="What needs to be covered?" /></label><label>Participants <em>comma-separated</em><input name="participants" placeholder="Asha, Dev, Priya" /></label><label>Raw notes<textarea name="raw_notes" required rows="5" placeholder="Capture discussion, decisions and follow-ups…" /></label><button className="primary" disabled={saving}><Plus size={17} /> {saving ? 'Saving…' : 'Save meeting'}</button></form></article><article className="panel"><PanelTitle eyebrow="MEETING HISTORY" title={`All meetings · ${meetings.length}`} />{meetings.length ? <div className="list all-meetings">{meetings.map((meeting) => <button className={`meeting-row ${selected?.id === meeting.id ? 'selected' : ''}`} key={meeting.id} onClick={() => { onSelect(meeting); onDiscard() }}><DateTile value={meeting.meeting_date} /><span><strong>{meeting.title}</strong><small>{meeting.agenda}</small></span><ChevronRight size={17} /></button>)}</div> : <Empty label="Meetings you save will appear here." />}{selected && <article className="detail"><p className="eyebrow">SELECTED MEETING</p><h3>{selected.title}</h3><p>{selected.raw_notes}</p><small><Users size={14} /> {selected.participants.join(', ') || 'No participants'} · {date(selected.meeting_date)}</small><button className="primary ai-button" onClick={onAnalyze} disabled={saving}>{saving ? 'Analyzing…' : 'Analyze notes with AI'}</button>{analysis && <div className="ai-review"><p className="eyebrow">REVIEW BEFORE SAVING</p><h3>AI meeting analysis</h3><p>{analysis.summary}</p><strong>Decisions</strong><ul>{analysis.decisions.length ? analysis.decisions.map((item) => <li key={item}>{item}</li>) : <li>None identified</li>}</ul><strong>Action items</strong><ul>{analysis.action_items.length ? analysis.action_items.map((item) => <li key={item.title}>{item.title} — {item.owner || 'Unassigned'}{item.due_date ? `, due ${date(item.due_date)}` : ''}</li>) : <li>None identified</li>}</ul>{analysis.blockers.length > 0 && <><strong>Blockers</strong><ul>{analysis.blockers.map((item) => <li key={item}>{item}</li>)}</ul></>}<div className="review-actions"><button className="primary" onClick={onApprove} disabled={saving}>Approve and save</button><button className="link" onClick={onDiscard}>Discard</button></div></div>}</article>}</article></section>
}

function Tasks({ meetings, tasks, filter, onFilter, onSave, onPatch, onCarry, saving }) { return <section className="content-grid tasks"><article className="panel"><PanelTitle eyebrow="MAKE WORK VISIBLE" title="New task" /><form className="form" onSubmit={onSave}><label>Task title<input name="title" required placeholder="Prepare release notes" /></label><label>Description <em>optional</em><textarea name="description" rows="3" placeholder="Add useful context…" /></label><div className="split"><label>Owner<input name="owner" placeholder="Name" /></label><label>Due date<input name="due_date" type="date" /></label></div><label>Origin meeting <em>optional</em><select name="origin_meeting_id"><option value="">No linked meeting</option>{meetings.map((meeting) => <option key={meeting.id} value={meeting.id}>{meeting.title}</option>)}</select></label><button className="primary" disabled={saving}><Plus size={17} /> {saving ? 'Saving…' : 'Create task'}</button></form></article><article className="panel"><div className="panel-title"><div><p className="eyebrow">WORKFLOW</p><h2>Tasks</h2></div><select className="filter" value={filter} onChange={(event) => onFilter(event.target.value)}><option>All</option>{statuses.map((item) => <option key={item}>{item}</option>)}</select></div>{tasks.length ? <div className="task-list">{tasks.map((task) => <article className="task" key={task.id}><div className="task-top"><div><h3>{task.title}</h3>{task.description && <p>{task.description}</p>}</div><Status value={task.status} /></div><div className="task-fields"><label>Owner<input defaultValue={task.owner || ''} placeholder="Unassigned" onBlur={(event) => (task.owner || '') !== event.target.value && onPatch(task.id, { owner: event.target.value || null })} /></label><label>Due date<input type="date" defaultValue={task.due_date || ''} onBlur={(event) => (task.due_date || '') !== event.target.value && onPatch(task.id, { due_date: event.target.value || null })} /></label><label>Status<select value={task.status} onChange={(event) => onPatch(task.id, { status: event.target.value })}>{statuses.map((item) => <option key={item}>{item}</option>)}</select></label></div>{task.status === 'Completed' && <label className="completion">Completion outcome<input defaultValue={task.completion_note || ''} placeholder="What was delivered?" onBlur={(event) => (task.completion_note || '') !== event.target.value && onPatch(task.id, { completion_note: event.target.value || null })} /></label>}{task.status !== 'Completed' && meetings.length > 0 && <label className="completion">Carry forward<select defaultValue="" onChange={(event) => { if (event.target.value) { onCarry(task.id, event.target.value); event.target.value = '' } }}><option value="">Select a meeting…</option>{meetings.map((meeting) => <option key={meeting.id} value={meeting.id}>{meeting.title}</option>)}</select></label>}{task.origin_meeting_id && <small className="origin">Linked to meeting #{task.origin_meeting_id}</small>}</article>)}</div> : <Empty label="No tasks match this view." />}</article></section> }
