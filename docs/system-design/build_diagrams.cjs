// Local, offline diagram renderer. Dependencies are supplied by the Codex runtime.
const fs = require('node:fs');
const path = require('node:path');
const { instance } = require('@viz-js/viz');
const sharp = require('sharp');
const base = __dirname;
const inv = JSON.parse(fs.readFileSync(path.join(base, 'inventory.json'), 'utf8'));
const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const q = s => JSON.stringify(s);
const artifacts = [];
const out = (file, text) => fs.writeFileSync(path.join(base, file), text);
for (const dir of ['sources', 'diagrams']) fs.mkdirSync(path.join(base, dir), {recursive: true});

function dot(title, body, direction='TB') {
  return `digraph G {
graph [rankdir=${direction}, bgcolor="white", pad="0.35", nodesep="0.48", ranksep="0.68", fontname="Arial", fontsize=22, fontcolor="#142d4e", labelloc=t, label=${q(title)}, splines=polyline];
node [shape=box, style="rounded,filled", fillcolor="#f0f6fc", color="#53769d", fontname="Arial", fontsize=13, fontcolor="#173454", margin="0.18,0.12", penwidth=1.2];
edge [fontname="Arial", fontsize=10, color="#637991", fontcolor="#344e68", arrowsize=0.7, penwidth=1.1];
${body}
}`;
}
function tableLabel(name, rows, type='') {
  return `< <TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0" CELLPADDING="7" COLOR="#6d87a3">`+
    `<TR><TD BGCOLOR="#173454"><FONT COLOR="white"><B>${esc(name)}</B>${type ? '<BR/>'+esc(type):''}</FONT></TD></TR>`+
    rows.map(r => `<TR><TD ALIGN="LEFT" BGCOLOR="#f3f7fb">${esc(r)}</TD></TR>`).join('')+'</TABLE> >';
}
function storeNode(id, label) {
  return `${id} [shape=plain, label=<<TABLE BORDER="1" SIDES="TB" CELLBORDER="0" CELLPADDING="9"><TR><TD>${esc(label)}</TD></TR></TABLE>>];`;
}
async function save(viz, id, title, source, caption) {
  out(`sources/${id}.dot`, source+'\n');
  const result=viz.render(source,{format:'svg',engine:'dot'});
  if(result.status !== 'success' || result.errors.some(e=>e.level==='error')) throw new Error(JSON.stringify(result.errors));
  if(result.errors.length) console.log(id, result.errors);
  await saveSvg(id,title,result.output,caption,'dot');
}
async function saveSvg(id,title,svg,caption,extension) {
  out(`diagrams/${id}.svg`,svg);
  const data=Buffer.from(svg);
  const metadata=await sharp(data).metadata();
  await sharp(data,{density:160}).resize({width:Math.min(3200,Math.max(1500,Math.ceil(metadata.width*1.6)))}).flatten({background:'#ffffff'}).png().toFile(path.join(base,`diagrams/${id}.png`));
  artifacts.push({id,title,caption,source:`sources/${id}.${extension}`,svg:`diagrams/${id}.svg`,png:`diagrams/${id}.png`,width:metadata.width,height:metadata.height});
}

async function main() {
 const viz=await instance();
 await save(viz,'01a-dfd-context','AutoTime | DFD Level 0 — context',dot('DFD Level 0 — AutoTime system boundary',`
 A [label="Admin", shape=box, style=filled, fillcolor="#fff1dc"];
 T [label="Teacher", shape=box, style=filled, fillcolor="#fff1dc"];
 S [label="Student / public viewer", shape=box, style=filled, fillcolor="#fff1dc"];
 E [label="SMTP email service", shape=box, style=filled, fillcolor="#e6f5ed"];
 P [label="0\nAutoTime\nTimetable Management", shape=ellipse, width=3, height=1.5, fillcolor="#dceafd"];
 A -> P [label="Account details; academic data; settings;\ngeneration / edit requests; leave decisions"];
 P -> A [label="Timetables; diagnostics; history;\nnotifications; Excel export"];
 T -> P [label="Credentials / OTP; timetable query;\nleave and profile requests"];
 P -> T [label="Live timetable; proxy assignments;\nrequest status; notifications"];
 S -> P [label="Registration / login; institute and\nclass / teacher timetable query"];
 P -> S [label="Account result; class / public timetable"];
 P -> E [label="Recipient and OTP email"];
 E -> P [label="SMTP delivery acceptance / error"];
 `,'LR'),'External entities exchange data with one AutoTime process. The database is internal and therefore omitted from the context diagram. Public timetable viewers are included because the current portal routes permit them.');

 await save(viz,'01b-dfd-level-1','AutoTime | DFD Level 1',dot('DFD Level 1 — principal processes and data stores',`
 A [label="Admin",fillcolor="#fff1dc",style=filled]; T [label="Teacher",fillcolor="#fff1dc",style=filled]; S [label="Student / public viewer",fillcolor="#fff1dc",style=filled]; E [label="SMTP service",fillcolor="#e6f5ed",style=filled];
 P1 [label="1.0\nManage identity\nand profile",shape=ellipse];
 P2 [label="2.0\nManage academic\ndata / settings",shape=ellipse];
 P3 [label="3.0\nGenerate and edit\nmaster timetable",shape=ellipse];
 P4 [label="4.0\nManage leave\nand proxies",shape=ellipse];
 P5 [label="5.0\nPresent timetables\nand exports",shape=ellipse];
 P6 [label="6.0\nPresent history\nand notifications",shape=ellipse];
 ${storeNode('D1','D1 Accounts / profile requests')}
 ${storeNode('D2','D2 Courses / subjects / configuration / calendar')}
 ${storeNode('D3','D3 Master and dated timetable entries')}
 ${storeNode('D4','D4 Teacher leave')}
 ${storeNode('D5','D5 Notifications / generation history')}
 A -> P1 [label="Account / profile data"]; T -> P1 [label="Credentials / profile data"]; S -> P1 [label="Registration / login"];
 P1 -> A [label="Account / profile result"]; P1 -> T [label="Account / request result"]; P1 -> S [label="Account result"];
 P1 -> E [label="OTP email"]; E -> P1 [label="Delivery result"];
 D1 -> P1 [label="Account records"]; P1 -> D1 [label="Verified account / update request"];
 P1 -> D5 [label="Profile-request alert"];
 A -> P2 [label="Master data / settings"]; P2 -> A [label="Saved data / validation"];
 D1 -> P2 [label="Teacher records"]; P2 -> D1 [label="Teacher changes"];
 P2 -> D2 [label="Academic changes"]; D2 -> P2 [label="Current data"];
 A -> P3 [label="Generate / edit request"]; P3 -> A [label="Result / diagnostics"];
 D1 -> P3 [label="Teacher constraints"]; D2 -> P3 [label="Requirements / slots"];
 D3 -> P3 [label="Existing slot data"]; P3 -> D3 [label="Validated schedule / slot update"];
 P3 -> D5 [label="Generation outcome"];
 T -> P4 [label="Leave / cancellation"]; A -> P4 [label="Approve / reject / revoke"];
 P4 -> T [label="Request result"]; P4 -> A [label="Decision result / leave status"];
 P4 -> D4 [label="Leave status"]; D4 -> P4 [label="Current leave"];
 D1 -> P4 [label="Available teachers"]; D2 -> P4 [label="Eligibility / configuration"];
 D3 -> P4 [label="Affected slots / workload"]; P4 -> D3 [label="Dated overrides / cleanup"];
 P4 -> D5 [label="Leave / proxy notifications"];
 A -> P5 [label="Class query / export"]; T -> P5 [label="Teacher / class query"]; S -> P5 [label="Class / public query"];
 D3 -> P5 [label="Master + dated rows"]; D2 -> P5 [label="Slots / class details"]; D1 -> P5 [label="Institute / teacher identity"];
 P5 -> A [label="Timetable / Excel"]; P5 -> T [label="Live timetable / proxy details"]; P5 -> S [label="Timetable"];
 A -> P6 [label="History / alerts query"]; T -> P6 [label="Alerts query"];
 D5 -> P6 [label="History / notifications"]; P6 -> D5 [label="Read flags / clear request"];
 P6 -> A [label="History / alerts"]; P6 -> T [label="Proxy / cancellation alerts"];
 `),'Logical DFD: each store groups existing tables, not a separate database. D1 = institute, teacher, student, teacher_update_request; D2 = course, subject, subject_courses, settings, academic_calendar; D3 = timetable; D4 = teacher_leave; D5 = notification, generation_history.');

 await save(viz,'01c-dfd-generation','AutoTime | Scheduling DFD decomposition',dot('DFD Level 2 — decompose process 3.0',`
 A [label="Admin",style=filled,fillcolor="#fff1dc"];
 ${storeNode('D1','D1 Accounts / teachers')} ${storeNode('D2','D2 Academic data / configuration')}
 ${storeNode('D3','D3 Timetable')} ${storeNode('D5','D5 Generation history')}
 R [label="3.1\nRead requirements\nand construct sessions",shape=ellipse];
 C [label="3.2\nCheck feasibility\nand find assignments",shape=ellipse];
 V [label="3.3\nOptimize and\naudit assignments",shape=ellipse];
 W [label="3.4\nPersist outcome",shape=ellipse];
 M [label="3.5\nValidate and apply\nmanual slot change",shape=ellipse];
 A -> R [label="Generation request"]; D1 -> R [label="Teacher constraints"]; D2 -> R [label="Subjects / classes / slots"];
 R -> C [label="Valid session occurrences"]; R -> W [label="Invalid-requirement diagnostics"];
 C -> V [label="Feasible assignment"]; C -> W [label="Failure / timeout diagnostics"];
 V -> W [label="Audited result / validation failure"];
 W -> D3 [label="Successful master replacement only"]; W -> D5 [label="Success / failure record"];
 W -> A [label="Outcome and diagnostics"];
 A -> M [label="Edit / assignment request"]; D1 -> M [label="Teacher identity"]; D2 -> M [label="Class / subject / slot details"]; D3 -> M [label="Current slots / conflicts"];
 M -> D3 [label="Accepted slot update"]; M -> A [label="Result / validation feedback"];
 `),'The detailed DFD keeps manual editing within process 3.0 and records generation failures without replacing the existing master timetable.');

 await save(viz,'03a-usecase-operations','AutoTime | Operational use cases',dot('Use-case diagram — timetable operations',`
 node [shape=ellipse]; edge [dir=none];
 A [shape=box,label="«actor»\nAdmin",fillcolor="#fff1dc"];
 T [shape=box,label="«actor»\nTeacher",fillcolor="#fff1dc"];
 S [shape=box,label="«actor»\nStudent",fillcolor="#fff1dc"];
 V [shape=box,label="«actor»\nPublic viewer",fillcolor="#fff1dc"];
 subgraph cluster_system { label="AutoTime"; color="#9fb3c8"; style=rounded;
  master [label="Manage courses, teachers\nand subjects / imports"];
  config [label="Manage settings\nand calendar"];
  generate [label="Generate timetable"];
  audit [label="Validate generated\nassignments"];
  edit [label="Edit / assign\ntimetable slots"];
  view [label="View class / teacher\nLive Week timetable"];
  export [label="Export Excel timetable"];
  history [label="View generation history"];
  leave [label="Request / cancel leave"];
  decide [label="Approve leave"];
  proxy [label="Attempt proxy allocation"];
  reject [label="Reject / revoke leave"];
  alerts [label="Read / clear notifications"];
  own [label="View own class timetable"];
  public [label="View public timetable"];
 }
 A -> master; A -> config; A -> generate; A -> edit; A -> export; A -> history; A -> decide; A -> reject; A -> alerts; A -> view;
 T -> leave; T -> view; T -> alerts; S -> own; V -> public;
 generate -> audit [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 decide -> proxy [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 `,'LR'),'Actors use valid UML rectangle notation with the «actor» stereotype. Admin, teacher and student operations require their corresponding sessions. Public timetable access is a separate implemented use case. PDF creation is client-side and is described in the frontend section.');

 await save(viz,'03b-usecase-accounts','AutoTime | Account use cases',dot('Use-case diagram — accounts and profile management',`
 node [shape=ellipse]; edge [dir=none];
 V [shape=box,label="«actor»\nVisitor / account applicant",fillcolor="#fff1dc"];
 U [shape=box,label="«actor»\nAuthenticated user",fillcolor="#fff1dc"];
 T [shape=box,label="«actor»\nTeacher",fillcolor="#fff1dc"];
 A [shape=box,label="«actor»\nAdmin",fillcolor="#fff1dc"];
 E [shape=box,label="«actor»\nEmail service",fillcolor="#e6f5ed"];
 subgraph cluster_system {label="AutoTime";color="#9fb3c8";style=rounded;
  reg [label="Register institute / student"];
  act [label="Activate existing teacher account"];
  otp [label="Verify email OTP"];
  login [label="Log in"];
  reset [label="Reset forgotten password"];
  profile [label="Update own profile"];
  request [label="Request teacher profile update"];
  approve [label="Approve / reject profile request"];
  pass [label="Change password"];
  remove [label="Delete own account"];
  logout [label="Log out"];
 }
 V -> reg; V -> act; V -> login; V -> reset;
 U -> profile; U -> pass; U -> remove; U -> logout;
 T -> request; A -> approve; E -> otp;
 reg -> otp [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 act -> otp [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 reset -> otp [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 remove -> otp [dir=forward,style=dashed,arrowhead=open,label="«include»"];
 `,'LR'),'Authenticated user denotes the shared actions available to signed-in roles; teacher name/email changes create an admin-reviewed request. Admin/student email changes require an OTP when the email changes.');

 const selected={Institute:['id','name','institute_code','admin_username'],Teacher:['id','teacher_id','name','available_days','max_hours'],Course:['id','class_id','department','semester','division'],Subject:['id','subject_code','subject_name','required_hours','session_length'],SubjectCourse:['subject_id','course_id','is_active'],Timetable:['id','day_name','start_time','session_group_id','specific_date','is_proxy'],Student:['id','name','email','class_id'],TeacherLeave:['id','teacher_id','date','start_time','status']};
 let classes='';
 for(const [name,keys] of Object.entries(selected)) {
   const table=inv.tables.find(t=>t.model===name);
   classes+=`${name} [shape=plain,label=${tableLabel(name,table.columns.filter(c=>keys.includes(c.name)).map(c=>`+ ${c.name}: ${c.type}`),'«SQLAlchemy model»')}];\n`;
 }
 classes+=`edge [dir=none];
 Institute -> Teacher [taillabel="0..1",headlabel="0..*"];
 Institute -> Course [taillabel="0..1",headlabel="0..*"];
 Institute -> Subject [taillabel="0..1",headlabel="0..*"];
 Institute -> Student [style=dashed,label="institute_code",taillabel="1",headlabel="0..*"];
 Teacher -> Subject [taillabel="0..1",headlabel="0..*"];
 Subject -> SubjectCourse [taillabel="1",headlabel="0..*"];
 Course -> SubjectCourse [taillabel="1",headlabel="0..*"];
 Course -> Student [style=dashed,label="class_id + institute_code",taillabel="1",headlabel="0..*"];
 Course -> Timetable [taillabel="0..1",headlabel="0..*"];
 Subject -> Timetable [taillabel="0..1",headlabel="0..*"];
 Teacher -> Timetable [taillabel="0..1",headlabel="0..*"];
 Teacher -> TeacherLeave [style=dashed,label="teacher_id + institute_code",taillabel="1",headlabel="0..*"];
 TeacherLeave -> Timetable [taillabel="0..1",headlabel="0..*"];`;
 await save(viz,'04a-class-domain','AutoTime | Domain classes',dot('Class diagram — core domain model',classes),'Selected attributes of the eight core model classes. Solid associations correspond to declared foreign keys; dashed associations are application-level links with intended cardinalities. Optional 0..1 reflects nullable FK columns. Supporting tables are covered in the complete ER and schema sections. Model classes define persistence fields, not invented business methods.');

 let engine='';
 const defs=[
 ['TimetableEngine',['+ time_slots: List[TimeSlot]','+ days: List[str]','+ generate(units, state)','- _presolve(units, state)','- _solve(units, state, depth)','- _optimize(units, state)']],
 ['SessionOccurrence',['+ id: str','+ subject_id: int','+ teacher_id: str','+ target_classes: List[str]','+ duration: int','+ assigned_slot: Optional[TimeSlot]']],
 ['TimeSlot',['+ day: str','+ idx: int','+ start_time: str','+ end_time: str']],
 ['GlobalState',['+ teacher_busy: dict','+ class_busy: dict','+ teacher_hours: dict','+ teacher_max_hours: dict','+ is_free(...) : bool','+ assign(...)','+ unassign(...)']],
 ['SchedulerConfig',['+ generation_timeout_seconds: float','+ optimization_timeout_seconds: float','+ optimization_max_iterations: int']],
 ['TimetableValidator',['+ audit(...) : tuple[bool, list]']],
 ['GenerationDiagnostics',['+ status: str','+ reason_code: str','+ primary_bottleneck: str','+ suggestions: List[str]','+ to_dict() : dict']],
 ['ScheduleConfig',['+ working_days: List[str]','+ total_lectures: int','+ lunch_after: int','+ get_dynamic_time_slots() : list']]
 ];
 for(const [name,rows] of defs) engine+=`${name} [shape=plain,label=${tableLabel(name,rows)}];\n`;
 engine+=`TimetableEngine -> TimeSlot [label="uses 0..*"]; TimetableEngine -> SessionOccurrence [label="schedules 0..*"];
 TimetableEngine -> GlobalState [label="reads / mutates",style=dashed]; TimetableEngine -> SchedulerConfig [label="configured by",style=dashed];
 TimetableEngine -> GenerationDiagnostics [label="returns",style=dashed]; TimetableEngine -> TimetableValidator [label="validates with",style=dashed];
 SessionOccurrence -> TimeSlot [label="assigned_slot 0..1"];
 TimetableValidator -> SessionOccurrence [label="audits",style=dashed];
 ScheduleConfig -> TimeSlot [label="adapter converts generated slots",style=dashed];`;
 await save(viz,'04b-class-scheduler','AutoTime | Scheduler classes',dot('Class diagram — scheduling implementation',engine),'Actual classes and representative attributes/methods from utils/scheduler and utils/helpers.py. The timetable adapter and leave service are modules of functions, so they are shown as components in the backend diagram rather than fictional classes.');

 const erFields={Institute:['id','institute_code','admin_email'],Teacher:['id','institute_id','teacher_id','institute_code','email'],Course:['id','institute_id','class_id','institute_code'],Subject:['id','institute_id','teacher_id_fk','subject_code','teacher_id','class_id'],SubjectCourse:['subject_id','course_id','is_active'],Timetable:['id','institute_id','course_id_fk','subject_id_fk','teacher_id_fk','leave_id','specific_date','session_group_id'],Student:['id','institute_code','class_id','email'],Settings:['id','institute_code','key','value'],TeacherLeave:['id','institute_code','teacher_id','date','status'],TeacherUpdateRequest:['id','institute_code','teacher_id','status'],AcademicCalendar:['id','institute_code','date','is_holiday'],Notification:['id','institute_code','user_type','user_id'],GenerationHistory:['id','institute_id','institute_code','status']};
 let er='';
 for(const t of inv.tables) {
  er+=`${t.table} [shape=plain,label=${tableLabel(t.table,t.columns.filter(c=>erFields[t.model].includes(c.name)).map(c=>`${c.pk?'PK ':c.references?'FK ':c.unique?'UK ':''}${c.name}${c.references&&c.nullable?' ?':''}`))}];\n`;
  for(const c of t.columns.filter(c=>c.references)) {
   const parent=c.references.split('.')[0];
   er+=`${parent} -> ${t.table} [dir=both,arrowtail=${c.nullable?'teeodot':'teetee'},arrowhead=crowodot,tooltip=${q(c.name+' -> '+c.references)}];\n`;
  }
 }
 er+=`subgraph cluster_legacy {label="No declared foreign keys on these five tables"; color="#c5b089"; style=dashed;
 student; settings; academic_calendar; teacher_update_request; notification;}
 institute -> student [style=invis];`;
 await save(viz,'05a-er-physical','AutoTime | Physical ER diagram',dot('ER diagram — all 13 declared tables',er),'Crow-foot notation: circle + crow = zero to many; circle + bar = zero or one; two bars = exactly one. All solid links come directly from models.py. The five tables in the dashed group have logical links documented separately, not enforced foreign keys. Selected columns shown; the data dictionary lists every column.');

 await save(viz,'05b-er-logical-links','AutoTime | Legacy logical relationships',dot('ER companion — application-level relationships',`
 I [label="institute\ninstitute_code"];
 T [label="teacher\n(institute_code, teacher_id)"];
 C [label="course\n(institute_code, class_id)"];
 S [label="student"]; ST [label="settings"]; AC [label="academic_calendar"];
 L [label="teacher_leave"]; R [label="teacher_update_request"]; N [label="notification"];
 edge [style=dashed,dir=none];
 I -> S [label="institute_code"]; I -> ST [label="institute_code"]; I -> AC [label="institute_code"];
 C -> S [label="institute_code + class_id"];
 T -> L [label="institute_code + teacher_id"];
 T -> R [label="institute_code + teacher_id"];
 T -> N [label="teacher recipient:\ninstitute_code + user_id = teacher_id"];
 I -> N [label="admin recipient:\ninstitute_code + user_type = admin"];
 `,'LR'),'Dashed links denote how application queries resolve relationships. They are not database-enforced foreign keys; orphaned legacy values remain possible at the schema level.');

 await save(viz,'06a-activity-generation','AutoTime | Generation activity',dot('Activity diagram — generate a master timetable',`
 start [shape=circle,label="",style=filled,fillcolor="#173454",width=0.2]; end [shape=doublecircle,label="",style=filled,fillcolor="#173454",width=0.2];
 auth [label="Validate admin session\nand CSRF token"];
 load [label="Load institute, subjects, teachers,\ncourses and schedule settings"];
 construct [label="Build periods and session occurrences"];
 valid [shape=diamond,label="Requirements\nvalid?"];
 solve [label="Presolve capacity; construct candidates;\nsearch feasible assignment"];
 found [shape=diamond,label="Feasible\nassignment?"];
 optimize [label="Optimize gaps / balance;\nrun engine validation"];
 audit [label="Independent adapter audit"];
 passed [shape=diamond,label="All constraints\nsatisfied?"];
 failure [label="Prepare failure diagnostics;\npreserve existing master",fillcolor="#fff1dc"];
 replace [label="Stage replacement of master rows only\n(specific_date IS NULL)",fillcolor="#e6f5ed"];
 history [label="Add generation history\nand commit transaction"];
 respond [label="Return JSON result to browser"];
 start -> auth -> load -> construct -> valid;
 valid -> solve [label="[yes]"]; valid -> failure [label="[no]"];
 solve -> found; found -> optimize [label="[yes]"]; found -> failure [label="[no / timeout]"];
 optimize -> audit -> passed; passed -> replace [label="[yes]"]; passed -> failure [label="[no]"];
 replace -> history; failure -> history; history -> respond -> end;
 `),'Main generation path after entry checks. No feasible assignment, invalid requirements and failed audits retain the existing master rows. Unexpected route exceptions return FAILED with INTERNAL_ERROR; a history row is not guaranteed for those exceptions.');

 await save(viz,'06b-activity-leave','AutoTime | Leave and proxy activity',dot('Activity diagram — leave approval and proxy assignment',`
 start [shape=circle,label="",style=filled,fillcolor="#173454",width=0.2]; end [shape=doublecircle,label="",style=filled,fillcolor="#173454",width=0.2];
 submit [label="Teacher submits valid leave request"];
 pending [label="Save Pending leave\nand admin notification"];
 decision [shape=diamond,label="Admin\ndecision?"];
 reject [label="Save Rejected status",fillcolor="#fff1dc"];
 approve [label="Stage Approved status"];
 affected [label="Find affected master-session blocks"];
 more [shape=diamond,label="More affected\nblocks?"];
 pick [label="Rank eligible proxy teachers:\nclass / department; subject; workload"];
 available [shape=diamond,label="Proxy\navailable?"];
 proxy [label="Stage dated proxy rows\nand teacher notification",fillcolor="#e6f5ed"];
 uncovered [label="Stage dated __UNCOVERED__ rows",fillcolor="#fff1dc"];
 commit [label="Commit status and overrides together"];
 view [label="Live Week merges dated rows\nover matching master slots"];
 start -> submit -> pending -> decision;
 decision -> reject [label="[reject]"]; reject -> end;
 decision -> approve [label="[approve]"]; approve -> affected -> more;
 more -> pick [label="[yes]"]; pick -> available;
 available -> proxy [label="[yes]"]; available -> uncovered [label="[no]"];
 proxy -> more; uncovered -> more; more -> commit [label="[no]"];
 commit -> view -> end;
 `),'Approval does not guarantee a substitute exists: uncovered dated rows hide the absent teacher. Service exceptions roll back the approval transaction. Cancellation/revocation deletes only rows tied to that leave_id and stores Cancelled; approved leave for today/past dates cannot be cancelled.');

 await save(viz,'08-deployment','AutoTime | Deployment',dot('Deployment diagram — configuration in this repository',`
 browser [shape=box3d,label="«device» User computer / phone\n«executionEnvironment» Web browser\nHTML / CSS / JavaScript",fillcolor="#fff1dc"];
 subgraph cluster_vercel {label="«node» Vercel deployment";color="#89a4c0";style=rounded;
 edgeRouter [shape=component,label="Configured request routing\nvercel.json: /(.*) → app.py"];
 runtime [shape=box3d,label="«executionEnvironment»\nPython function / Flask app"];
 app [shape=note,label="«artifact» app.py + routes + utils\nmodels.py + templates + static"];
 runtime -> app [style=dashed,label="hosts"];
 edgeRouter -> runtime [label="forward request"];
 }
 pg [shape=cylinder,label="«database» PostgreSQL\nSupabase per project README\nPersistent application tables",fillcolor="#e6f5ed"];
 smtp [shape=box3d,label="«external service» Gmail SMTP\nsmtp.gmail.com:465"];
 cdn [shape=box3d,label="«external service» Frontend CDNs\nBootstrap / Turbo / Tom Select\nfonts / html2pdf.js"];
 browser -> edgeRouter [label="HTTPS requests / responses",dir=both];
 runtime -> pg [label="SQLAlchemy + psycopg2\nDATABASE_URL connection",dir=both];
 runtime -> smtp [label="SMTP over SSL / OTP mail"];
 browser -> cdn [label="HTTPS asset requests"];
 `,'LR'),'Repository-configured deployment, not an audit of the live Vercel account. PostgreSQL is the documented production database; local development defaults to SQLite. Database TLS depends on DATABASE_URL/provider configuration and is not asserted here.');

 await save(viz,'09-frontend-architecture','AutoTime | Frontend architecture',dot('Frontend architecture — server-rendered pages with JavaScript',`
 route [label="Flask route handlers\nrender_template(context)",fillcolor="#e6f5ed"];
 base [label="Jinja shared/base.html\nRole navigation; theme; CSRF meta; flash UI"];
 roles [label="Page templates\nauth / admin / teacher / student / shared"];
 component [label="Reusable components\npublic_navbar.html\nTimetable view-model: days_data"];
 browser [label="Browser DOM",fillcolor="#fff1dc"];
 ui [label="Bootstrap 5 + icons + Inter\nTom Select; Turbo navigation"];
 global [label="static/js/main.js + base scripts\nCSRF form fields; theme; loaders;\ntoasts; sidebar preferences"];
 page [label="Page-level JavaScript\nGeneration fetch; class lookup\nslot forms; PDF export"];
 api [label="JSON endpoints\n/api/generate_timetable\n/api/get_classes/<inst_code>\n/api/get_slot_data"];
 styles [label="static/style.css + loader.css\nResponsive layouts and styling"];
 local [shape=cylinder,label="Browser localStorage\ntheme / sidebar preferences"];
 pdf [label="Local PDF output\nTeacher: html2pdf.js\nStudent: window.print()"];
 route -> base [label="renders"]; base -> roles [label="content blocks"]; base -> component [label="includes / context"];
 roles -> browser [label="HTML response"]; component -> browser;
 styles -> browser; ui -> browser; global -> browser; page -> browser;
 global -> local [label="read / write",dir=both]; browser -> route [label="GET / POST forms + session cookie"];
 page -> api [label="fetch / JSON"]; page -> pdf;
 `),'Pages extend the shared Jinja layout; this repository is not a React SPA. PDF export is executed in the browser, while Excel export is returned by Flask. components/timetable.html exists but active inclusion was not found, so it is not shown as an active rendering dependency.');

 await save(viz,'10-backend-architecture','AutoTime | Backend architecture',dot('Backend architecture — Flask modules and persistence',`
 http [label="HTTP request",fillcolor="#fff1dc"];
 factory [label="app.py / create_app()\nConfiguration; SQLAlchemy; healthz"];
 security [label="utils/security.py\nCSRF validation; session setup; headers"];
 bp [label="routes/blueprint.py\nSingle main_bp blueprint"];
 auth [label="routes/auth.py\nAccounts / OTP / settings"];
 admin [label="routes/admin.py\nMaster data; generation; editing;\nleave decisions; Excel export"];
 teacher [label="routes/teacher.py\nActivation; views; leave; alerts"];
 student [label="routes/student.py\nRegistration; public / private views"];
 guards [label="utils/decorators.py\nRole session guards"];
 adapter [label="utils/timetable_adapter.py\nORM ↔ scheduling objects\nMaster + dated Live Week merge"];
 engine [label="utils/scheduler/\ncore / engine / validator / diagnostics"];
 leave [label="utils/leave_service.py\nApprove / cancel; atomic proxy changes"];
 proxy [label="utils/proxy_engine.py\nEligibility and ranked proxy selection"];
 helpers [label="utils/helpers.py + timetable_helpers.py\nScheduleConfig; OTP / SMTP; view model"];
 models [label="models.py\n13 SQLAlchemy models / tables"];
 db [shape=cylinder,label="PostgreSQL (production)\nSQLite fallback (local)",fillcolor="#e6f5ed"];
 view [label="Jinja templates / JSON / file response"];
 http -> factory -> security -> bp;
 bp -> auth; bp -> admin; bp -> teacher; bp -> student;
 guards -> admin [style=dashed]; guards -> teacher [style=dashed]; guards -> student [style=dashed];
 admin -> adapter; teacher -> adapter; student -> adapter;
 admin -> leave; teacher -> leave; leave -> proxy;
 adapter -> engine; adapter -> models; leave -> models; proxy -> models;
 auth -> helpers; admin -> helpers; teacher -> helpers; student -> helpers;
 auth -> models; admin -> models; teacher -> models; student -> models;
 models -> db; auth -> view; admin -> view; teacher -> view; student -> view;
 `),'A modular Flask application with one blueprint, not separate deployed microservices. The route modules also query models directly; the diagram does not invent a repository layer, task queue, or background worker.');

 await sequence('07a-sequence-generation','Sequence — generate timetable',
  ['Admin browser','Flask route','Timetable adapter','Engine / validator','Database'],[
   {from:0,to:1,text:'POST /api/generate_timetable + session / CSRF'},
   {from:1,to:1,text:'Check CSRF and admin session'},
   {from:1,to:2,text:'engine_generate_timetable(institute_code)'},
   {from:2,to:4,text:'Read institute, subjects, teachers, courses, settings'},
   {from:4,to:2,text:'Academic data and constraints',reply:true},
   {from:2,to:2,text:'Build time slots and session occurrences'},
   {from:2,to:3,text:'generate(units, state)',note:'Only when weekly requirements are valid'},
   {from:3,to:2,text:'success, schedule, message, stats, diagnostics',reply:true},
   {from:2,to:3,text:'TimetableValidator.audit(...)',note:'Only after engine success'},
   {from:3,to:2,text:'Audit result / errors',reply:true},
   {frame:'alt',text:'[generation and audit succeed]'},
   {from:2,to:4,text:'Replace master rows; add SUCCESS history; commit'},
   {branch:'[requirements / generation / audit fail]'},
   {from:2,to:4,text:'Keep master; add FAILED history; commit'},
   {end:true},
   {from:2,to:1,text:'Result dictionary',reply:true},
   {from:1,to:0,text:'HTTP 200 JSON; inspect success / status',reply:true},
  ],'Invalid requirements skip the engine. Unexpected route exceptions return INTERNAL_ERROR; the final response still normally has HTTP 200. JSON business failure must be checked via success/status.');

 await sequence('07b-sequence-leave','Sequence — leave approval and live timetable',
 ['Teacher browser','Flask routes','Admin browser','Leave / proxy modules','Database'],[
  {from:0,to:1,text:'POST /apply_leave + form / CSRF'},
  {from:1,to:4,text:'Create Pending leave + admin notification; commit'},
  {from:1,to:0,text:'Redirect to teacher dashboard',reply:true},
  {from:2,to:1,text:'POST /admin/approve_leave/<leave_id>'},
  {from:1,to:3,text:'approve_leave(leave_id, institute_code)'},
  {from:3,to:4,text:'Load Pending leave; stage Approved status'},
  {from:3,to:4,text:'Read affected master blocks, teachers and workload'},
  {from:4,to:3,text:'Session blocks and candidate information',reply:true},
  {frame:'loop',text:'[for every affected session block]'},
  {from:3,to:3,text:'find_best_proxy(...)'},
  {frame:'alt',text:'[eligible proxy found]'},
  {from:3,to:4,text:'Stage dated proxy rows + teacher notification'},
  {branch:'[no eligible proxy]'},
  {from:3,to:4,text:'Stage dated __UNCOVERED__ rows'},
  {end:true},{end:true},
  {from:3,to:4,text:'Commit approved leave and all overrides'},
  {from:3,to:1,text:'Success / message (rollback on exception)',reply:true},
  {from:1,to:2,text:'Redirect to leave requests',reply:true},
  {from:0,to:1,text:'GET /teacher_dash'},
  {from:1,to:4,text:'Read master and current-week dated entries'},
  {from:4,to:1,text:'Rows for effective schedule merge',reply:true},
  {from:1,to:0,text:'Rendered Live Week timetable',reply:true},
 ],'Admin and teacher requests are distinct HTTP interactions. Every approval groups status and overrides in one database transaction. The adapter merges dated rows over matching weekly master slots before filtering a teacher view.');

 out('diagram-manifest.json',JSON.stringify(artifacts,null,2)+'\n');
 console.log(`Rendered ${artifacts.length} diagrams to SVG and PNG; all Graphviz sources parsed successfully.`);
}

async function sequence(id,title,actors,steps,caption) {
 const w=1600, left=115, spacing=(w-230)/(actors.length-1), xs=actors.map((_,i)=>left+i*spacing);
 const positions=[]; let y=160;
 for(const step of steps){positions.push(y);y+=step.frame||step.branch?48:step.end?24:step.note?80:64;}
 const h=y+70; const elems=[]; const text=(x,y,s,anchor='middle',size=16)=>`<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="Arial" font-size="${size}" fill="#173454">${esc(s)}</text>`;
 elems.push(`<rect width="${w}" height="${h}" fill="white"/>`,text(w/2,42,title,'middle',26));
 for(let i=0;i<actors.length;i++){
  elems.push(`<rect x="${xs[i]-107}" y="76" width="214" height="48" rx="5" fill="#eaf2fb" stroke="#53769d"/>`,text(xs[i],106,actors[i]));
  elems.push(`<line x1="${xs[i]}" x2="${xs[i]}" y1="124" y2="${h-30}" stroke="#a3b3c4" stroke-dasharray="7 6"/>`);
 }
 const stack=[]; const frames=[];
 steps.forEach((s,i)=>{if(s.frame)stack.push({start:positions[i],step:s,depth:stack.length});if(s.end){const f=stack.pop();f.end=positions[i]+8;frames.push(f);}});
 if(stack.length)throw new Error('Unclosed sequence frame');
 for(const f of frames){const inset=25+f.depth*15;elems.push(`<rect x="${inset}" y="${f.start-24}" width="${w-2*inset}" height="${f.end-f.start+24}" fill="none" stroke="#7189a3"/>`,text(inset+10,f.start-2,f.step.frame+' '+f.step.text,'start',15));}
 let plant=`@startuml\ntitle ${title}\nhide footbox\nskinparam backgroundColor white\nskinparam sequenceMessageAlign center\n`;
 actors.forEach((a,i)=>plant+=`participant "${a}" as P${i}\n`);
 steps.forEach((s,i)=>{
  const yy=positions[i];
  if(s.frame){plant+=`${s.frame} ${s.text}\n`;return;}
  if(s.branch){elems.push(`<line x1="25" x2="${w-25}" y1="${yy-24}" y2="${yy-24}" stroke="#7189a3" stroke-dasharray="7 4"/>`,text(50,yy-2,s.branch,'start',15));plant+=`else ${s.branch}\n`;return;}
  if(s.end){plant+='end\n';return;}
  const x1=xs[s.from],x2=xs[s.to],dash=s.reply?' stroke-dasharray="7 4"':'';
  if(s.from===s.to){
   elems.push(`<path d="M ${x1} ${yy} h 75 v 22 h -75" fill="none" stroke="#42658a" marker-end="url(#arrow)"/>`,text(x1+8,yy-10,s.text,'start',14));
  }else{
   elems.push(`<line x1="${x1}" x2="${x2}" y1="${yy}" y2="${yy}" stroke="#42658a"${dash} marker-end="url(#${s.reply?'open':'arrow'})"/>`);
   const label=esc(s.text); const mid=(x1+x2)/2; const approx=s.text.length*7.3;
   elems.push(`<rect x="${mid-approx/2-5}" y="${yy-24}" width="${approx+10}" height="20" fill="white"/>`,text(mid,yy-9,s.text,'middle',14));
  }
  if(s.note)elems.push(text((x1+x2)/2,yy+28,s.note,'middle',13));
  plant+=`P${s.from} ${s.reply?'-->':'->'} P${s.to}: ${s.text}\n`;
  if(s.note)plant+=`note over P${s.from}, P${s.to}: ${s.note}\n`;
 });
 plant+='@enduml\n';out(`sources/${id}.puml`,plant);out(`sources/${id}.sequence.json`,JSON.stringify({title,actors,steps,caption},null,2)+'\n');
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0 L9 4 L0 8 Z" fill="#42658a"/></marker><marker id="open" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0 L9 4 L0 8" fill="none" stroke="#42658a"/></marker></defs>${elems.join('')}</svg>`;
 await saveSvg(id,title,svg,caption,'puml');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
