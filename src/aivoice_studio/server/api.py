"""Flask API server — wraps AI Cover Studio pipeline behind HTTP."""

from __future__ import annotations

import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_file

from aivoice_studio.core.context import JobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.server.feishu import feishu
from aivoice_studio.ui.model_config_map import ModelConfigMap
from aivoice_studio.utils.config import ConfigLoader
from aivoice_studio.utils.paths import project_root, resolve_path

app = Flask(__name__)
app.register_blueprint(feishu)

_state = {
    "model": "G_16000", "pitch": 0, "reverb": "关闭",
    "total_covers": 0, "last_cover": "", "last_time": 0.0,
}

cfg = ConfigLoader().load()
MODEL_MAP = ModelConfigMap(cfg.get("svc", {}).get("models_dir", "models"))
UPLOAD_DIR = project_root() / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Cover Studio</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei",sans-serif;background:#121212;color:#e8e8e8;min-height:100vh}
.wrap{max-width:960px;margin:0 auto;padding:20px}
.hero{text-align:center;padding:48px 0 32px}
.hero h1{color:#1ed760;font-size:36px;margin-bottom:8px}
.hero p{color:#888;font-size:16px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px}
@media(max-width:640px){.grid{grid-template-columns:1fr}}
.about{background:#1a1a1a;border-radius:16px;padding:28px}
.about h2{color:#1ed760;font-size:18px;margin-bottom:12px}
.about ol{color:#b3b3b3;font-size:14px;line-height:2;padding-left:20px}
.about li::marker{color:#1ed760;font-weight:700}
.about p,.about li{color:#b3b3b3;font-size:14px;line-height:1.8}
.card{background:#1a1a1a;border-radius:16px;padding:32px 28px}
.upload{border:2px dashed #2a2a2a;border-radius:12px;padding:28px;text-align:center;cursor:pointer;margin-bottom:16px}
.upload:hover{border-color:#1ed760}
.upload p{font-size:15px;color:#b3b3b3}
.upload .icon{font-size:36px;margin-bottom:8px}
select,input[type=range]{width:100%;background:#121212;border:1px solid #2a2a2a;border-radius:8px;padding:10px;color:#e8e8e8;font-size:14px;margin:4px 0}
.row{display:flex;gap:12px;text-align:left;margin:6px 0}
.row label{color:#888;font-size:12px}
.row div{flex:1}
.btn{background:#1ed760;border:none;border-radius:24px;padding:14px;color:#121212;font-size:16px;font-weight:800;cursor:pointer;width:100%}
.btn:disabled{background:#2a2a2a;color:#555}
.result{margin-top:12px;padding:12px;background:#121212;border-radius:8px;font-size:13px;color:#b3b3b3;text-align:center}
.result a{color:#1ed760;font-size:15px;font-weight:700}
.progress{height:4px;background:#2a2a2a;border-radius:2px;margin-top:12px;overflow:hidden}
.progress div{height:100%;background:#1ed760;width:0;transition:width .3s}
.footer{text-align:center;color:#555;font-size:12px;padding:32px 0 16px}
.footer a{color:#1ed760}
</style>
</head>
<body>
<div class="wrap">
<div class="hero">
  <h1>♫ AI Cover Studio</h1>
  <p>本地 AI 翻唱工具 · 上传歌曲 · 一键翻唱</p>
</div>
<div class="grid">
<div class="about">
  <h2>📖 这是什么</h2>
  <p>AI Cover Studio 是一个本地运行的 AI 翻唱工具。上传任意歌曲，AI 自动分离人声、转换成目标音色、混合伴奏，输出完整翻唱 MP3。全程本地处理，不依赖云端。</p>
  <h2 style="margin-top:16px">🛠 使用步骤</h2>
  <ol>
    <li>点击或拖拽上传一首歌</li>
    <li>选择音色模型和音高</li>
    <li>点击「生成翻唱」</li>
    <li>下载翻唱 MP3</li>
  </ol>
  <h2 style="margin-top:16px">🎤 当前音色</h2>
  <p>{{ model_list }}</p>
  <h2 style="margin-top:16px">⏱ 处理速度</h2>
  <p>约 1 分钟 / 首歌（GPU 加速）</p>
  <h2 style="margin-top:16px">🔒 隐私</h2>
  <p>所有处理在本地完成，歌曲不会上传到任何云端</p>
</div>
<div class="card">
  <div class="upload" id="drop">
    <div class="icon">📁</div>
    <p>拖拽或点击上传歌曲</p>
    <p style="font-size:12px;color:#555;margin-top:4px">MP3 · WAV · FLAC · M4A</p>
    <input type="file" id="file" accept="audio/*" style="display:none">
  </div>
  <div class="row">
    <div><label>音色模型</label><select id="model">{{ model_options|safe }}</select></div>
    <div><label>音高</label><input type="range" id="pitch" min="-12" max="12" value="0"><span id="pv" style="color:#1ed760;font-size:13px">0</span></div>
  </div>
  <div class="row">
    <div><label>混响</label><select id="reverb"><option>关闭</option><option>录音棚</option><option>现场</option><option>大教堂</option></select></div>
  </div>
  <button class="btn" id="go">生成翻唱</button>
  <div id="stages" style="display:none;margin:16px 0;text-align:left">
    <div id="s1" style="color:#555;font-size:13px;padding:4px 0">○ 人声分离 UVR</div>
    <div id="s2" style="color:#555;font-size:13px;padding:4px 0">○ 歌声转换 SVC</div>
    <div id="s3" style="color:#555;font-size:13px;padding:4px 0">○ 混音导出</div>
  </div>
  <div class="progress" id="pw" style="display:none"><div id="prog"></div></div>
  <div class="result" id="result"></div>
</div>
</div>
<div class="footer">由 so-vits-svc + audio-separator + ffmpeg 驱动 · 已生成 {{ count }} 首</div>
</div>
<script>
const d=document.getElementById('drop'),f=document.getElementById('file');
d.onclick=()=>f.click();
d.ondragover=e=>{e.preventDefault();d.style.borderColor='#1ed760'};
d.ondragleave=()=>d.style.borderColor='#2a2a2a';
d.ondrop=e=>{e.preventDefault();d.style.borderColor='#2a2a2a';f.files=e.dataTransfer.files};
f.onchange=()=>d.querySelector('p').textContent='✓ '+f.files[0].name;
document.getElementById('pitch').oninput=function(){
  document.getElementById('pv').textContent=(this.value>0?'+':'')+this.value;
};
function tick(i,t,el,txt){setTimeout(()=>{el.innerHTML=txt;el.style.color='#1ed760'},t)}
function doneAll(){['s1','s2','s3'].forEach(id=>{let e=document.getElementById(id);e.innerHTML=e.innerHTML.replace('○','✓')})}
document.getElementById('go').onclick=async()=>{
  const fl=f.files[0];
  if(!fl){alert('请先选择音频文件');return}
  const b=document.getElementById('go'),r=document.getElementById('result');
  const p=document.getElementById('prog'),w=document.getElementById('pw'),st=document.getElementById('stages');
  b.disabled=true;b.textContent='处理中…';st.style.display='block';w.style.display='block';p.style.width='0';
  ['s1','s2','s3'].forEach(id=>{let e=document.getElementById(id);e.innerHTML=e.innerHTML.replace('✓','○');e.style.color='#555'});
  let t0=Date.now(),timer=setInterval(()=>{let e=(Date.now()-t0)/1000,s1=document.getElementById('s1'),s2=document.getElementById('s2'),s3=document.getElementById('s3');if(e<20){s1.innerHTML='● 人声分离 UVR  '+Math.round(e*100/20)+'%';p.style.width=Math.min(e*5,40)+'%'}else if(e<55){s1.innerHTML='✓ 人声分离 UVR';s2.innerHTML='● 歌声转换 SVC  '+Math.round((e-20)*100/35)+'%';p.style.width=Math.min(40+(e-20)*1.5,85)+'%'}else{s1.innerHTML='✓ 人声分离 UVR';s2.innerHTML='✓ 歌声转换 SVC';s3.innerHTML='● 混音导出';p.style.width=Math.min(85+(e-55)*3,98)+'%'}},300);
  const fd=new FormData();
  fd.append('audio',fl);fd.append('model',document.getElementById('model').value);
  fd.append('pitch',document.getElementById('pitch').value);fd.append('reverb',document.getElementById('reverb').value);
  try{
    const x=await fetch('/api/cover',{method:'POST',body:fd});
    clearInterval(timer);doneAll();p.style.width='100%';
    if(!x.ok){const e=await x.json();throw new Error(e.error||'失败')}
    const blob=await x.blob(),url=URL.createObjectURL(blob),dn=fl.name.replace(/\.[^.]+$/,'')+'_cover.mp3';
    r.innerHTML=`<audio controls src="${url}" style="width:100%;height:36px;margin-bottom:8px"></audio><br><a href="${url}" download="${dn}">⬇ 下载 MP3</a>`;
  }catch(e){clearInterval(timer);r.innerHTML=`<span style="color:#e74c3c">✗ ${e.message}</span>`}
  b.disabled=false;b.textContent='生成翻唱';
  setTimeout(()=>{w.style.display='none';st.style.display='none';p.style.width='0'},5000);
};
</script>
</body>
</html>"""


@app.route("/")
def index():
    models = MODEL_MAP.list_models() or ["G_16000"]
    opts = "\n".join(f'<option value="{m}">{m}</option>' for m in models)
    return render_template_string(
        INDEX_HTML, model_options=opts, model_list=", ".join(models),
        count=_state["total_covers"],
    )


@app.route("/api/models")
def api_models():
    return jsonify({"models": MODEL_MAP.list_models()})


@app.route("/api/status")
def api_status():
    return jsonify(_state)


@app.route("/api/cover", methods=["POST"])
def api_cover():
    f = request.files.get("audio")
    if not f:
        return jsonify({"error": "请上传音频文件"}), 400

    ext = Path(f.filename or "audio.mp3").suffix or ".mp3"
    upload_path = UPLOAD_DIR / f"input_{uuid.uuid4().hex[:8]}{ext}"
    f.save(str(upload_path))

    model = request.form.get("model", _state["model"])
    pitch = int(request.form.get("pitch", _state["pitch"]))
    reverb = request.form.get("reverb", _state["reverb"])
    _state.update(model=model, pitch=pitch, reverb=reverb)

    try:
        pipeline, config = build_pipeline()
        rt = config.get("runtime", {})
        result = pipeline.run(JobContext(
            input_audio=upload_path, model_name=model, pitch=pitch,
            f0_method="rmvpe",
            workdir=resolve_path(rt.get("workdir", "workdir")),
            output_dir=resolve_path(rt.get("output_dir", "outputs")),
            export_mp3=True, reverb=reverb,
        ))
        if not result.success:
            return jsonify({"error": result.error or "处理失败"}), 500
        mp3_path = Path(result.mp3_path) if result.mp3_path else None
        if not mp3_path or not mp3_path.exists():
            return jsonify({"error": "未找到输出文件"}), 500
        _state["total_covers"] += 1
        return send_file(str(mp3_path), mimetype="audio/mpeg",
                         as_attachment=True,
                         download_name=f"{upload_path.stem}_cover.mp3")
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try:
            upload_path.unlink()
        except OSError:
            pass
