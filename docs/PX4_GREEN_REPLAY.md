# 綠燈模型離線仿真回放

更新：2026-10-15。這一階段把實際提供的 AXMODEL 接入模擬彩色影像回放。
現有 PX4 飛行任務仍用原 Python 裝甲矩形辨識；本工具不改任務或飛控輸入。
藍色實心矩形保留；新回放不提取它的輪廓、尺寸或位姿。模型 ROI 仍含周邊背景，
模型是否依賴背景尚未驗證。VIO 和下視 AprilTag 保持現有接口。

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

回放信心門檻現採作者 `fd7ff39` 的 `tools/model/board_center_replay.py`
及 `board_center_validator.cpp` 使用的 0.3。先前 0.5 來自通用配置，
此次修正依據上游中心回放工具；實機部署門檻仍未核對。
RGB、uint8、320×320、裁切、step 2 抽樣、雙線性 letterbox 114 和座標還原
已依原始碼核對規則；主機／板端逐像素等價尚未驗證，模型及裁切策略未改。

本輪為 headless 離線錄製 AXMODEL 張量回放，使用相同保存 RGB 與先前真正
執行的模型輸出；新推理數為零。40 幀的結果如下：

| 項目 | 舊 0.5 配置 | 上游中心回放 0.3 配置 |
| --- | --- | --- |
| 模型肯定候選 | 14/40 | 27/40 |
| 有效當幀追蹤輸出 | 17/40 | 28/40 |
| 黑圖期間有效輸出 | 0 | 0 |
| 黑圖後恢復原視角序列 | 未重獲 | 恢復後第二幀重新確認 |
| 整段持續追蹤 | 未通過 | 未通過 |

一次模型否定可暫時沿用尚未過期的肯定，所以有效輸出數可多於模型肯定數。
新版名義片段第 1–28 幀有效，第 29–39 幀持續失鎖。全部 40 幀都有像素候選；
13 次模型拒絕均由分類信心不足引起，沒有出現關鍵點／坐標關聯拒絕。
這些計數不是人工標註準確率，也不能證明訓練資料與仿真成像存在何種差異。
應結合實機部署配置和有標註的實機影像再研究，而非繼續在此片段調門檻。

有限功能檢查通過：黑圖／無目標不輸出、恢復原視角序列與合成重現可重獲；
9 項接口和模型解碼測試通過。C++ 與飛控程式本輪未改，未重跑飛行批次。
無目標測試使用全黑圖，不能解讀為真實干擾物誤檢率。

新本地證據索引：`artifacts/green-replay-diagnosis-closeout-01/summary.json`。
含 `comparison.png`、`nominal.mp4`、`blackout.mp4` 和全部診斷／回放摘要。
視覺倉庫 `tools/drone_replay/diagnose.py` 可重建對照圖及上游來源哈希。
上一輪證據仍在 `artifacts/green-replay-closeout-01/summary.json`。

早期嘗試保留了候選未進入模型、張量檔名匹配錯誤、NumPy 計數的 JSON
序列化錯誤，以及重新渲染後輸入 bytes 改變而拒絕重用的結果。
成功回放使用原保存彩色圖的精確模型輸入；新匯出器核對素材，並另保存新圖。
本地 `slam_drone` 開發提交及 PX4 的子倉庫引用已保存；尚未發布新增提交。

## 後段失鎖的有限輸入對照

固定幀 8、26、30、39，候選、ROI 和 0.3 門檻保持相同；原 RGB 使用核對
哈希的既有張量，另一組經主機 RGB→NV21 及原 C++ NV21→RGB，再實際
執行 4 次 AXMODEL。這只是合成色彩轉換，不能代表實機原始 NV21。

| 幀 | 原 RGB 最大分類信心 | 轉回 RGB 最大分類信心 |
| --- | --- | --- |
| 8 | 0.74155 | 0.25845 |
| 26 | 0.04062 | 0.01454 |
| 30 | 0.10832 | 0.00864 |
| 39 | 0.00864 | 0.00179 |

三張失鎖影像沒有恢復，原本通過的一張也降至門檻以下。預設回放仍使用
原 RGB。這個有限對照顯示模型對像素變化敏感，沒有找到足以解釋後段失鎖
的接入修正；背景、尺度和訓練資料的影響仍未辨明。

MaixCDK 官方固定提交 `30f4b8b7e3f66ded9cfa64fb081b46e30bc27248` 的分類、
DFL 與關鍵點公式和主機解碼規則一致，仍未認證部署端 SDK／像素等價。
視覺倉庫新增 `tools/drone_replay/input_probe.py` 及 C++ 診斷轉換入口，
推理前固定案例並保存輸入／输出哈希；10 項相關測試通過。

本輪索引：`artifacts/green-input-probe-closeout-01/summary.json`。
包含兩次嘗試（首次舊資料索引讀取失敗）、對照圖、逐幀分數、官方來源快照
及測試記錄。`passed` 僅表示有限診斷完成；先前 28/40 輸出與未通過的
連續追蹤結論保持原證據範圍。本輪沒有重跑完整回放或 PX4 飛行。

## 實機影片輸入索引

2026-10-15 收到一段作者／實機研究用影片，已保存原始檔案哈希並完成格式
檢查：`1344×760`、名義 `180 FPS`、`13766` 幀、`76.4778 s`，SHA256
為 `437d72cb003c0db33d1ea8377b2d61e234280813dbb83c85ab3c8e3e44fe50bb`。
影片包含綠燈可見、視角變化及目標場景；目前只完成索引和抽樣預覽，尚未
將它送入 AXMODEL 回放，也沒有把影片內容當成仿真或飛行通過證據。

作者倉庫目前可查到的板端中心模型規則是 `320×320`、分類門檻 `0.3`、
關鍵點門檻 `0.35`（`tools/model/board_center_replay.py` 與
`board_center_validator.cpp`）；通用 `config/green_detector.conf`
仍是 NPU 關閉、`256` 輸入、`0.50` 門檻的工程起始配置。實際部署應用
正在由作者繼續更新，本分支暫不自行改動辨識核心或門檻。

索引產物位於本機 ignored 目錄：
`artifacts/real-green-clip-inspection-01/video_metadata.json` 和
`preview.jpg`。原始影片不加入 Git；後續作者更新後再用同一影片做有限
回歸，並與本輪仿真結果分開報告。
