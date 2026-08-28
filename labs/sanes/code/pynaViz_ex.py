import pynapple as nap
import pynaviz as viz
import numpy as np
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget, QSizePolicy


from pynaviz.controller_group import ControllerGroup



# Load NWB file
# data = nap.load_file('/Users/thoman1/Documents/EMBER/Code/Sanes/NWB_Files/sanesData_0.nwb')
data = nap.load_file('/Users/thoman1/Documents/EMBER/Code/Sanes/NWB_Files/sanesData_v2.nwb')
print(data)
#print(data['Multi-channel Audio Data'])
audioData = data['Multi-channel Acoustic Data']
#audioData = data['Multi-channel Audio Data']

print(audioData.shape)
endTime = (audioData.end_time('s'))
print(endTime)
#print(data['External Behavioral Video'])
sound = data['Multi-channel Acoustic Data']
# sound = data['Multi-channel  Data']
sound.channels = np.arange(12)
# print(sound)
v1 = viz.TsdFrameWidget(sound)
v1.plot.sort_by('channels')
#v2 = viz.PlotTsdTensor(data['External Behavioral Video'])
#v2 = viz.TsdTensorWidget(data['External Behavioral Video'])
#v2 = viz.VideoWidget(data['External Behavioral Video'])

# v2 = viz.VideoWidget('/Users/thoman1/Documents/EMBER/Code/Sanes/Example Data/idx_0/center-session_135_video-0.mp4',t=np.linspace(0,endTime,10800))

v2 = viz.VideoWidget('/Users/thoman1/Documents/EMBER/Code/Sanes/Example Data/combined_output.mp4')
print(v2.plot.data.shape)

nframes = v2.plot.data.shape[0]
v2 = viz.VideoWidget('/Users/thoman1/Documents/EMBER/Code/Sanes/Example Data/combined_output.mp4',t=np.linspace(0,endTime,nframes))





# Qt Application
app = QApplication([])
window = QWidget()
window.setMinimumSize(1500, 800)
layout1 = QVBoxLayout()

# --- Size policy fixes ---
v1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
v2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

# layout2 = QVBoxLayout()

ctrl_group = ControllerGroup()
ctrl_group.add(v2, 0)
ctrl_group.add(v1, 1)


layout1.addWidget(v2)
layout1.addWidget(v1)

# layout1.setStretch(0, 1)  # v2 gets 1 unit
# layout1.setStretch(1, 2)  # v1 gets 2 units


#layout1.addLayout(layout2)
window.setLayout(layout1)
window.show()

if __name__ == "__main__":
    app.exit(app.exec())

# Controller group
#ctrl_group = ControllerGroup([v1, v2])

# v = viz.VideoWidget('/Users/thoman1/Documents/EMBER/Code/Sanes/Example Data/idx_0/center-session_135_video-0.mp4')

#v1.show()
# v.show()