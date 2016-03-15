import DeepInstruments as di
import librosa
import matplotlib.pyplot as plt
import numpy as np

# Parameters for audio
decision_length = 131072  # in samples
fmin = 55  # in Hz
hop_length = 1024  # in samples
n_bins_per_octave = 12
n_octaves = 8

# Get single-label split (MedleyDB for training, solosDb for test
(test_stems, training_stems) = di.singlelabel.get_stems()

# Compute audio features and retrieve melodies on the training set
datagen = di.singlelabel.ScalogramGenerator(
        decision_length, fmin, hop_length,
        n_bins_per_octave, n_octaves,
        training_stems)

# Compute audio features on the test set
test_paths = di.singlelabel.get_paths("test")
X_test = datagen.get_X(test_paths)
y_test = np.hstack(map(di.descriptors.get_y, test_paths))

# Parameters for ConvNet
is_spiral = True

conv1_channels = 32
conv1_height = 7
conv1_width = 3
pool1_height = 3
pool1_width = 6
conv2_channels = 32
conv2_height = 21
conv2_width = 7
pool2_height = 3
pool2_width = 6
dense1_channels = 32

# Parameters for learning
batch_size = 32
epoch_size = 8192
n_epochs = 20
optimizer = "adam"
spiral_str = "sp-" if is_spiral else ""
export_str = spiral_str +\
             str(conv1_channels) + "x" +\
             str(conv1_height) + "x" +\
             str(conv1_width) + "-" +\
             str(pool1_height) + "x" +\
             str(pool1_width) + "-" +\
             str(conv2_channels) + "x" +\
             str(conv2_height) + "x" +\
             str(conv2_width) + "-" +\
             str(pool2_height) + "x" +\
             str(pool2_width) + "-" +\
             str(dense1_channels)

# I/O sizes
X_width = decision_length / hop_length
dense2_channels = 8
X_height = n_bins_per_octave * n_octaves
mask_width = X_width / pool1_width
mask_height = X_height / pool1_height
masked_output = np.zeros((batch_size, 1, mask_height, mask_width))
names = [name.split(" ")[0] for name in di.singlelabel.names]

# Build ConvNet as a Keras graph, compile it with Theano
graph = di.learning.build_graph(
    is_spiral,
    n_bins_per_octave,
    n_octaves,
    X_width,
    conv1_channels,
    conv1_height,
    conv1_width,
    pool1_height,
    pool1_width,
    conv2_channels,
    conv2_height,
    conv2_width,
    pool2_height,
    pool2_width,
    dense1_channels,
    dense2_channels)
graph.compile(loss={"Y": "categorical_crossentropy"}, optimizer=optimizer)

# Train ConvNet
if is_spiral:
    offset = 0.75  # measured empirically as X_batch mean
else:
    offset = 0.33
from keras.utils.generic_utils import Progbar
batch_losses = np.zeros(epoch_size / batch_size)
chunk_accuracies_history = []
file_accuracies_history = []
mean_loss = float("inf")

for epoch_id in xrange(n_epochs):
    dataflow = datagen.flow(batch_size=batch_size, epoch_size=epoch_size)
    print "\nEpoch ", 1 + epoch_id
    progbar = Progbar(epoch_size)
    batch_id = 0
    for (X_batch, Y_batch) in dataflow:
        loss = di.learning.train_on_batch(graph, is_spiral,
                                          X_batch, Y_batch, offset)
        batch_losses[batch_id] = loss[0]
        progbar.update(batch_id * batch_size)
        batch_id += 1
    if np.mean(batch_losses) < mean_loss:
        mean_loss = np.mean(batch_losses)
        std_loss = np.std(batch_losses)
    else:
        break
    print "\nTraining loss = ", mean_loss, " +/- ", std_loss

    # Measure test accuracies
    class_probs = di.learning.predict(graph, is_spiral, X_test, offset)
    y_predicted = np.argmax(class_probs, axis=1)
    chunk_accuracies = di.singlelabel.chunk_accuracies(y_predicted, y_test)
    chunk_accuracies_history.append(chunk_accuracies)
    file_accuracies = di.singlelabel.file_accuracies(test_paths, y_predicted,
                                                     y_test)
    file_accuracies_history.append(file_accuracies)
    mean_file_accuracy = np.mean(file_accuracies)
    std_file_accuracy = np.std(file_accuracies)
    mean_chunk_accuracy = np.mean(chunk_accuracies)
    std_chunk_accuracy = np.std(chunk_accuracies)
    print "----------------------------"
    print "            CHUNK     FILE  "
    for name_index in range(len(names)):
        print names[name_index],\
            " " * (9 - len(names[name_index])),\
            " " * (chunk_accuracies[name_index] < 100.0),\
            round(chunk_accuracies[name_index], 1), "  ",\
            " " * (file_accuracies[name_index] < 100.0),\
            round(file_accuracies[name_index], 1), "  "
    print "----------------------------"
    print "GLOBAL      ",\
        round(mean_chunk_accuracy, 1), "    ",\
        round(mean_file_accuracy, 1)
    print "std      (+/-" +\
        str(round(0.5 * std_chunk_accuracy, 1)) +\
        ") (+/-" +\
        str(round(0.5 * std_file_accuracy, 1)) + ")"

# Save final scores
final_chunk_score = chunk_accuracies_history[-1]
final_mean_chunk_score = np.mean(final_chunk_score)
final_file_score = file_accuracies_history[-1]
final_mean_file_score = np.mean(final_file_score)

# Save results
np.savez(
    export_str + ".npz",
    decision_length=decision_length,
    fmin=fmin,
    hop_length=hop_length,
    n_bins_per_octave=n_bins_per_octave,
    n_octaves=n_octaves,
    conv1_channels=conv1_channels,
    conv1_height=conv1_height,
    conv1_width=conv1_width,
    pool1_height=pool1_height,
    pool1_width=pool1_width,
    conv2_channels=conv2_channels,
    conv2_height=conv2_height,
    conv2_width=conv2_width,
    pool2_height=pool2_height,
    pool2_width=pool2_width,
    dense1_channels=dense1_channels,
    batch_size=batch_size,
    epoch_size=epoch_size,
    n_epochs=n_epochs,
    optimizer=optimizer,
    chunk_accuracies_history=chunk_accuracies_history,
    file_accuracies_history=file_accuracies_history,
    final_chunk_score=final_chunk_score,
    final_mean_chunk_score=final_mean_chunk_score,
    final_file_score=final_file_score,
    final_mean_file_score=final_mean_file_score)

# Save weights
graph.save_weights(export_str + ".h5", overwrite=True)

# Save images for first-layer kernels
if is_spiral:
    for j in range(6):
        octave_index = 6 * j + 4
        octave = graph.get_weights()[octave_index]
        kernels = [octave[i, 0, :, :] for i in range(conv1_channels)]
        zero_padding = 0.0 * np.ones((conv1_height, 1))
        kernels = [np.concatenate((kernel, zero_padding), axis=1)
                   for kernel in kernels]
        kernels = np.hstack(kernels)
        librosa.display.specshow(kernels)
        plt.savefig(export_str + "-j" + str(j) + ".png")
else:
    first_layer = graph.get_weights()[0]
    kernels = [first_layer[i, 0, :, :] for i in range(conv1_channels)]
    zero_padding = -0.0 * np.ones((conv1_height, 1))
    registered_kernels = [np.concatenate((kernel, zero_padding), axis=1)
                          for kernel in kernels]
    librosa.display.specshow(np.hstack(kernels))
    plt.savefig(export_str + ".png")

# For Fig 3
librosa.display.specshow(X_test[0][0, 0, :, :] - 0.5)
