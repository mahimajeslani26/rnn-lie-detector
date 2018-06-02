tf.flags.DEFINE_float("lr", 0.001, "learning rate")
tf.flags.DEFINE_integer('epochs', 5, 'number of epoch')
tf.flags.DEFINE_integer("hidden_size", 256, "hidden size for each layer")
tf.flags.DEFINE_integer('batch_size', 1, 'batch size')
tf.flags.DEFINE_integer('eval_every', 200,
                        'evaluation after number of train steps')
tf.flags.DEFINE_bool('normalize', False, 'normalize feature data')
tf.flags.DEFINE_float('dropout', 0.2, 'dropout rate')
tf.flags.DEFINE_string('model', 'GRU', 'RNN, GRU or LSTM')
tf.flags.DEFINE_string('data_dir', 'data', 'directory of original data files')
tf.flags.DEFINE_string('test_data_dir', 'test_data', 'directory of testing data files')
tf.flags.DEFINE_string('log_dir', 'tmp/runs/', 'directory to save log file')
tf.flags.DEFINE_bool('per_frame', True, 'RNN on per frame (row) data instead '
                                        'of taking the whole MFCC vector ')


FLAGS = tf.app.flags.FLAGS

tf.logging.set_verbosity(tf.logging.INFO)


class Params(object):
    """ hyper-parameters """
    lr = FLAGS.lr
    epochs = FLAGS.epochs
    hidden_size = FLAGS.hidden_size
    batch_size = FLAGS.batch_size
    train_steps = 0
    eval_steps = 0
    predict_steps = 0
    eval_every = FLAGS.eval_every
    normalize = FLAGS.normalize
    dropout = FLAGS.dropout
    model = FLAGS.model
    data_dir = FLAGS.data_dir
    test_data_dir = FLAGS.test_data_dir
    log_dir = FLAGS.log_dir
    num_classes = 3
    feature_length = 13
    max_length = 0
    per_frame = FLAGS.per_frame


def generate_data(params):
    """ Extract data and transcript from FLAGS.data_dir
    Note: 0 indicate True, 1 indicate Lie Up, 2 indicate Lie Down for labels
    """
    if not os.path.exists(params.data_dir):
        print("Data directory %s not found" % params.data_dir)
        exit()
    features = []
    labels = []
    sequence_length = []
    for subdir, dirs, files in os.walk(params.data_dir):
        for speaker in dirs:
           # print( speaker)
            with open(os.path.join(
                    params.data_dir, speaker, 'transcripts.txt'), 'r') as f:
                transcripts = f.readlines()
            if not transcripts:
                continue
            files = sorted(fnmatch.filter(os.listdir(
                os.path.join(params.data_dir, speaker)), '*npy'))

            assert len(transcripts) == len(files)
	   # print (transcripts)

            for i in range(len(transcripts)):
                # read MFCC vector from npy file
                features.append(np.load(
                    os.path.join(FLAGS.data_dir, speaker, files[i])))
                # read label from transcripts
                label = transcripts[i].split()[1]
                if label.startswith('T'):
                    labels.append(0)
 ray
    features, labels = np.asarray(features), np.asarray(labels)

    # normalize features
    if params.normalize:
        shape = features.shape
        # normalize function only takes 2D matrix
        features = np.reshape(features, newshape=(shape[0], shape[1] * shape[2]))
        features = normalize(features, norm='l2')
        features = np.reshape(features, newshape=shape)

    assert features.shape[0] == labels.shape[0] == len(sequence_length)

    # randomly shuffle data
    features, labels, sequence_length = \
        shuffle(features, labels, sequence_length, random_state=1)

    return features, labels, sequence_length

def metric_fn(labels, predictions):
    """ Metric function for evaluations"""
    return {'eval_accuracy': tf.metrics.accuracy(labels, predictions),
            'eval_precision': tf.metrics.precision(labels, predictions),
            'eval_recall': tf.metrics.recall(labels, predictions)}


def rnn(features, mode, params):
    """ Recurrent model """
    if params.model == "LSTM":
        cell = BasicLSTMCell(params.hidden_size)
    elif params.model == "GRU":
        cell = GRUCell(params.hidden_size)
    else:
        cell = BasicRNNCell(params.hidden_size)

    initial_state = cell.zero_state(params.batch_size, dtype=tf.float64)

    if params.per_frame:
        # convert input from (batch_size, max_time, ...) to
        # (max_time, batch_size, ...)
        inputs = tf.transpose(features['feature'], [1, 0, 2])

        sequence_length = tf.reshape(
            features['sequence_length'],
            shape=(params.batch_size,)
        )

        outputs, state = tf.nn.dynamic_rnn(
            cell,
            inputs=inputs,
            initial_state=initial_state,
            sequence_length=sequence_length,
            time_major=True
        )

        # get output from the last state
        outputs = outputs[features['sequence_length'][0] - 1]
    else:
        # reshape MFCC vector to fit in one time step
        inputs = tf.reshape(
            features['feature'],
            shape=(1, params.batch_size, params.max_length * params.feature_length)
        )

        outputs, state = tf.nn.dynamic_rnn(
            cell,
            inputs=inputs,
            initial_state=initial_state,
            time_major=True
        )

        outputs = tf.reshape(
            outputs,
            shape=(params.batch_size, params.hidden_size)

    # apply dropout
    dropout = tf.layers.dropout(
        outputs,
        rate=params.dropout,
        training=mode == tf.estimator.ModeKeys.TRAIN
    )

    logits = tf.layers.dense(
        dropout,
        units=params.num_classes,
        activation=None
    )

    return logits


def model_fn(features, labels, mode, params):
    """ Estimator model function"""

    print ("inside model_fn")

    logits = rnn(features, mode, params)

    predictions = tf.argmax(tf.nn.softmax(logits), axis=-1)
    predictions = tf.Print(predictions, [predictions], "prediction: ")
   
    loss = tf.reduce_mean(
        tf.nn.sparse_softmax_cross_entropy_with_logits(
            labels=labels,
            logits=logits
        )
    )
   # loss= tf.Print(loss, [loss], "loss: ")

    train_op = tf.train.AdamOptimizer(params.lr).minimize(
        loss=loss,
        global_step=tf.train.get_global_step()
    )

    # metrics summary
    tf.summary.text('prediction', tf.as_string(predictions))
    tf.summary.text('label', tf.as_string(labels))
    accuracy = tf.metrics.accuracy(labels, predictions)
    tf.summary.scalar('training_accuracy', accuracy[1])
    precision = tf.metrics.precision(labels, predictions)
    tf.summary.scalar('training_precision', precision[1])
    recall = tf.metrics.recall(labels, predictions)
    tf.summary.scalar('training_recall', recall[1])
   # accuracy =tf.Print(accuracy, [accuracy])
