# 綠燈模型離線仿真回放

日期：2026-10-13。這一階段把實際提供的 AXMODEL 接入模擬彩色影像回放。
現有 PX4 飛行任務仍用原 Python 裝甲矩形辨識；本工具不改任務或飛控輸入。
藍色實心矩形保留，但新回放不使用它。VIO 和下視 AprilTag 保持現有接口。

## 來源與界線

開發來源為 `blademaster679/maixcam2_dart_vision` 的 `slam_drone`，已整合固定
上游 `fd7ff396994f0da69c67573ef4b52c531abc1e6b`。共用 C++ 候選搜尋、像素中心、
模型確認和卡爾曼濾波；主機 Pulsar2 6.0 執行已量化的 NPU 模型。
板端非同步調度沒有移植至此離線模式，後續實機確認另行安排。

目前原始 RGB 沒有完整保存在該次飛行產物中；此工具從原錄製 qpos/qvel
重新渲染場景。圖片因此是**錄製狀態重建**，不是當時實際送到感知端的原始像素。
原時間戳保留，場景與已有素材哈希核對；物理狀態只進入匯出器，辨識器只讀 RGB。
現有相機為 800×600、70°、20 Hz 的仿真假設，不能當作 OS04A10 實測標定。

## 產生 RGB 輸入

```bash
cd /home/shiuhou/Projects/rm27_drones_px4
MUJOCO_GL=egl /home/shiuhou/venvs/mujoco/bin/python \
  -m rm27.perception.sitl.green_replay_export \
  artifacts/px4-prototype-closeout-02/flight \
  --config configs/px4_prototype_camera.json \
  --start 60 --duration 2 --output artifacts/green-rgb-input-new
```

`--start` 為原仿真時鐘秒數，`--duration` 為半開區間長度；不從處理幀率重建時間。
若錄製資料具有 `route_audit.json`，會核對場景素材哈希；缺少時明確報告
`source_assets_verified: false`，不宣稱已核對完整素材。
輸出包括彩色 PNG、微秒時間戳、配置及圖片哈希。

## 建置與模型回放

視覺倉庫的 `tools/drone_replay/README.md` 提供完整命令與模型 I/O 說明。
本機開發路徑：
`/home/shiuhou/Projects/rm27_drones/rm27/perception/vision/maixcam2_dart_vision`。
模型在 `/home/shiuhou/Projects/`，Pulsar2 6.0 在本工作區
`artifacts/deps/pulsar2-6.0/ax_pulsar2_6.0_lite_package/`。
模型、工具包、原始圖片、影片及結果均留在 ignored artifacts／本地路徑。

回放需指定 `--manifest`、`--mud`、`--toolchain`、`--library`、`--output`。
先使用 `--limit 1` 核對實際推理，再使用短片段與 `--expect-target present`。
此功能檢查要求至少兩幀有效量測，不是完整片段的精度驗收。
`--reuse-inference` 核對相同模型、輸入 bytes、工具和輸出哈希後可重用原推理；
摘要會明確標示錄製張量回放。

模型對應的原始訓練數據／訓練權重尚未取得；只使用關鍵點 0，不推斷其餘點
具有可靠監督。仿真模型分類效果和真實干擾物表現需分別評估。

## 測試與判讀

主機 C++ 回歸覆蓋共用來源，新增測試覆蓋 20 Hz 確認、同軌跡否定、
時間倒退／重複、失鎖與重獲、RGB bytes 和 Pose 解碼。
名義短片段使用實際模型；黑圖遮擋與重獲可重用完全相同輸入的模型張量。
全黑片段檢查無像素時保持無效，不作真實誤檢率證據。

讀取实际 `summary.json`；分别檢查 `pipeline_passed`、`tracking_check_passed`、
`fresh_model_inferences` 和 `recorded_model_inferences_used`。
`model_positive` 是通過模型與像素關聯的候選數，`observed_frames` 是軌跡
確認後具有當幀像素的有效輸出數。兩者不等同於人工標註的識別準確率。
`safe_for_control` 保持 false，這些輸出未完成 PX4 控制接入資格驗證。

局部亮核心長寬比從原預設 4 擴展到無人機回放配置 8，處理斜視下的標記。
濾波和確認時限依來源幀週期配置。這些調整沒有模型再訓練或幾何改造。

最終本地證據索引：`artifacts/green-replay-closeout-01/summary.json`。

本次結果：名義片段 40 次模型推理中 14 次候選肯定，17 幀有效追蹤輸出。
一次模型否定可暫時沿用尚未過期的肯定，所以有效輸出數可多於模型肯定數。
直接遮擋後沒有自然重獲；重複早期視角的明確合成 fixture 驗證了重獲程式。
連續辨識與自然重獲未通過，沒有降低模型門檻來掩蓋這個結果。

早期嘗試保留了候選未進入模型、張量檔名匹配錯誤、NumPy 計數的 JSON
序列化錯誤，以及重新渲染後輸入 bytes 改變而拒絕重用的結果。
成功回放使用原保存彩色圖的精確模型輸入；新匯出器核對素材，並另保存新圖。
本地 `slam_drone` 開發提交及 PX4 的子倉庫引用已保存；尚未發布新增提交。
