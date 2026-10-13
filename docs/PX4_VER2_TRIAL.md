# Ver2 機體模型檢查與 PX4 首次試跑

2026-10-13，使用者指定的模型為：
`/home/shiuhou/Projects/rm27_drones/rm_mjcf/rm27_drone_mjcf/`。
本次讀取README、配置、模型與來源hash後，在新目錄進行模型檢查、
機庫沉降及一次PX4短程任務。原模型庫和原主工作區程式保持原狀。

## README與實際模型

本版為Ver2，150 g含電池，約114 × 114 × 45 mm。保留5系列框架、
移除3系列框架、補上30 × 65 × 5 mm核心板。靜態版只有外觀；
動態版有自由機體、4路濾波推力致動器、246個剛性碰撞代理。
控制量為每電機牛頓推力，並非PWM或歸一化油門。

馬達XY位置為±27.5 mm，+Z升力，yaw符號+／−／+／−。
最大推力1.103625 N／路、40 ms遲滯及0.018 m yaw torque／thrust
仍為工程估計。慣量採均勻外包絡盒估計
`[0.0001877625, 0.0001877625, 0.0003249] kg m²`，
暫定重心在底部上方22.5 mm。這些配置不代表真機校準。

## PX4接口適配

舊PX4仿真配置使用30 mm馬達位置及20 mm底部高度，本次完成兩項
模型接口修正，沒有調整MC／MPC控制增益或模型物理參數：

- 從編譯後的旋翼site與actuator gear，生成PX4的NED／FRD allocator
  位置與KM，保留物理motor_0..3的順序；檢查單位+Z推力及旋向力矩。
- 落地高度從模型bottom site讀取；Ver2為22.5 mm，歷史代理仍為20 mm。
  真值只供獨立物理評分，短程任務用PX4估計進行導航。

生成的試跑場景保留CAD網格、四機體質量、慣量、旋翼位置、推力、
濾波器和碰撞數量。僅將生成副本的機體group設為5以配合現有range
排除規則；沒有修改原runtime包。輸入／素材hash記錄在
`artifacts/px4-ver2-ekf-probe-20261013-01/plant/inputs.json`。

## 本次實際結果

| 項目 | 結果及證據 |
| --- | --- |
| 模型級13 s動作檢查 | 通過；原主工作區 `artifacts/ver2-user-model-check-20261013-01/summary.json`。便攜載入、150 g、旋翼力矩、開放槳區、懸停、平移、返回及接地均通過；是MuJoCo真值回饋，沒有飛控 |
| 四機體無動力沉降 | 通過；原主工作區 `artifacts/ver2-user-dock-20261013-01/settling.json`。5 s後停穩，初始無接觸；最大接觸力0.3364 N、穿透0.3616 mm；不是多機飛行 |
| PX4 v1.17.0短程試跑 | **1/1通過**；`artifacts/px4-ver2-ekf-probe-20261013-01/summary.json`。headless閉環SITL，起飛→10 s懸停→0.12 m平移→返回→LAND→自動停槳；仿真79.896 s |
| 估計來源 | 合成ODOMETRY到EKF2，任務用PX4遙測。ULog確認EV位置／速度／yaw實際融合；沒有GPS或真實VIO／相機输入 |
| 懸停真值評分 | 最大水平4.083 mm／高度45.825 mm，p95為3.895／45.296 mm |
| 落地真值評分 | 水平4.632 mm；實際停靠高度22.4987 mm；停槳、接地與物理靜止確認通過 |
| 錄製電機輸入回放 | **19,966幀通過，最大狀態誤差0**；`artifacts/px4-ver2-ekf-replay-20261013-01/summary.json`。不是另一次閉環飛行 |
| ULog | 解碼／融合檢查通過；`artifacts/px4-ver2-ekf-ulog-20261013-01/summary.json` |
| 接口與根測試 | 受影響檢查32通過；根測試**462通過、5跳過**，記錄於 `artifacts/px4-ver2-{interface,root}-tests-20261013-01.log` |

以上毫米數值來自MuJoCo真值評分，不是相機或真機精度。只跑一次
代表性短任務，沒有為幾厘米精度進行增益搜索或大批次重複。
完整接觸／恢復／圖像回庫仍需用這個新碰撞模型另建證據；旧代理
完整任務的通過不能直接轉移到Ver2。

## 重現

主工作區建立新Ver2機庫場景及模型檢查：

```bash
cd /home/shiuhou/Projects/rm27_drones
MUJOCO_GL=egl /home/shiuhou/venvs/mujoco/bin/python \
  -m rm27.integration.validate_drone_v2 --package rm_mjcf/rm27_drone_mjcf \
  --output artifacts/ver2-model-check-new
/home/shiuhou/venvs/mujoco/bin/python -m rm27 build-dock \
  --config configs/scene_v2.json --output artifacts/ver2-dock-new
```

在PX4工作區試跑，明確傳入外部模型與配置：

```bash
cd /home/shiuhou/Projects/rm27_drones_px4
/home/shiuhou/venvs/mujoco/bin/python -m rm27.autopilot.px4.vehicle_probe \
  /home/shiuhou/Projects/rm27_drones/artifacts/ver2-dock-new/scene.xml \
  --package /home/shiuhou/Projects/rm27_drones/rm_mjcf/rm27_drone_mjcf \
  --vehicle-config /home/shiuhou/Projects/rm27_drones/configs/drone_v2.json \
  --output artifacts/px4-ver2-probe-new --instance 70 --profile ekf
```

每次用新目錄；查看實際summary。`--profile ekf`為合成外部定位診斷，
`flow`／`mtf`為既有數值感測選項，本次沒有試跑後兩者。
模型庫有未提交的Ver2更新，復現需相同runtime文件與hash，不能只
依賴其舊Git提交。大型CAD／網格沒有加入PX4程式倉庫。

沒有硬件操作、模型庫發布或參數寫入；本次程式變更在獨立PX4
worktree，原主倉庫的其他修改與歷史結果保留。
