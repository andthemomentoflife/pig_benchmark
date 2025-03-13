import argparse
from configobj import ConfigObj
from configobj.validate import Validator
import importlib
import logging
import os
import sys
import time

import tensorflow as tf
from tensorflow.python import debug as tf_debug

from ctalearn.image_mapping import image_mapper
from ctalearn.data_loading import DataLoader
from ctalearn.data_processing import DataProcessor

# Disable Tensorflow info and warning messages (not error messages)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
tf.logging.set_verbosity(tf.logging.WARN)

def setup_logging(config, log_dir, debug, log_to_file):

    # Log configuration to a text file in the log dir
    time_str = time.strftime('%Y%m%d_%H%M%S')
    config_filename = os.path.join(log_dir, time_str + '_config.ini')
    with open(config_filename, 'w') as config_file:
        config.write(config_file)

    # Set up logger
    logger = logging.getLogger()
    
    if debug: logger.setLevel(logging.DEBUG)
    
    logger.handlers = [] # remove existing handlers from any previous runs
    if not log_to_file:
        handler = logging.StreamHandler()
    else:
        logging_filename = os.path.join(log_dir, time_str + '_logfile.log')
        handler = logging.FileHandler(logging_filename)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logger.addHandler(handler)
    
    return logger

def run_model(config, mode="train", debug=False, log_to_file=False):

    # Load options relating to logging and checkpointing
    model_dir = config['Logging']['model_directory']
    # Create model directory if it doesn't exist already
    if not os.path.exists(model_dir): os.makedirs(model_dir)

    # Set up logging, saving the config and optionally logging to a file
    logger = setup_logging(config, model_dir, debug, log_to_file)
    
    # Load options to specify the model
    sys.path.append(config['Model']['model_directory'])
    model_module = importlib.import_module(config['Model']['model_module'])
    model = getattr(model_module, config['Model']['model_function'])
    model_type = config['Model']['model_type']
    
    model_hyperparameters = config['Model']['Model Parameters']
    
    # Load options related to the data format and location
    data_format = config['Data']['format']
    data_files = []
    with open(config['Data']['file_list']) as f:
        for line in f:
            line = line.strip()
            if line and line[0] != "#":
                data_files.append(line)

    # Load options related to image mapping
    image_mapping_settings = config['Image Mapping']

    # Load options related to data loading
    if mode == "train":
        data_loader_mode = "train"
    elif mode == "predict":
        data_loader_mode = "test"

    data_loading_settings = config['Data']['Loading']
    data_loading_settings['mode'] = data_loader_mode
    data_loading_settings['example_type'] = model_type

    # Load options related to data processing
    apply_processing = config['Data']['apply_processing']
    data_processing_settings = config['Data']['Processing']
    data_processing_settings['num_shower_coordinates'] = 2, # position on camera needs 2 coords

    # Load options related to data input
    data_input_settings = config['Data']['Input']
    if data_format == 'HDF5':
        data_input_settings['map'] = True

    # Load options related to training hyperparameters
    training_hyperparameters = config['Training']['Hyperparameters']
    training_hyperparameters['model_type'] = model_type
    training_hyperparameters['variables_to_train'] = config['Model']['variables_to_train'] 
    
    # Load other options related to training 
    num_epochs = config['Training']['num_epochs']
    train_forever = False if num_epochs == 0 else True
    num_training_steps_per_validation = config['Training']['num_training_steps_per_validation']

    # Load options related to prediction if needed
    if mode == 'predict':
        true_labels_given = config['Prediction']['true_labels_given']
        export_prediction_file = config['Prediction']['export_as_file']
        if export_prediction_file:
            prediction_path = config['Prediction']['prediction_file_path']
        # Don't allow parallelism in predict mode. This can lead to errors
        # when reading from too many open files at once.
        data_input_settings['num_parallel_calls'] = 1
    
    # Load options related to debugging
    run_tfdbg = config['Debug']['run_TFDBG']

    # Instantiate data processor
    if apply_processing:
        data_processor = DataProcessor(
                image_mapper=image_mapper(**image_mapping_settings),
                **data_processing_settings)
    else:
        data_processor = None

    # Define data loading functions
    if data_format == 'HDF5':

        data_loader = HDF5DataLoader(
                data_files,
                mode=data_loader_mode,
                data_processor=data_processor,
                **data_loading_settings)

        # Define format for Tensorflow dataset
        # Build dataset from generator returning (HDF5_filename, index) pairs
        # and a load_data function which maps (HDF5_filename, index) pairs
        # to full training examples (images and labels)
        data_input_settings['generator_output_types'] = data_loader.generator_output_types
        data_input_settings['map'] = True
        data_input_settings['map_func'] = lambda *x: tuple(tf.py_func(data_loader.get_example,
            x, data_loader.data_types))
        data_input_settings['output_names'] = data_loader.output_names
        data_input_settings['outputs_are_label'] = outputs_are_label
    
        # Get data generators returning (filename,index) pairs from data files 
        # by applying cuts and splitting into training and validation
        if mode == 'train':
            training_generator, validation_generator, class_weights = data_loader.get_example_generators()
        elif mode == 'predict':
            test_generator, class_weights = data_loader.get_example_generators()

        training_hyperparameters['class_weights'] = class_weights

    else:
        raise ValueError("Invalid data format: {}".format(data_format))

    # Define input function for TF Estimator
    def input_fn(generator, settings): 
        # NOTE: Dataset.from_generator takes a callable (i.e. a generator
        # function / function returning a generator) not a python generator
        # object. To get the generator object from the function (i.e. to
        # measure its length), the function must be called (i.e. generator())
        dataset = tf.data.Dataset.from_generator(generator,
                settings['generator_output_types'])
        if settings['shuffle']:
            dataset = dataset.shuffle(settings['shuffle_buffer_size'])
        if settings['map']:
            dataset = dataset.map(settings['map_func'],
                    num_parallel_calls=settings['num_parallel_calls'])
        dataset = dataset.batch(settings['batch_size'])
        if settings['prefetch']:
            dataset = dataset.prefetch(settings['prefetch_buffer_size'])
    
        iterator = dataset.make_one_shot_iterator()

        # Return a batch of features and labels. For example, for an
        # array-level network the features are images, triggers, and telescope
        # positions, and the labels are the gamma-hadron labels
        iterator_outputs = iterator.get_next()
        features = {}
        labels = {}
        for output, output_name, is_label in zip(
                iterator_outputs,
                settings['output_names'],
                settings['outputs_are_label']):
            if is_label:
                labels[output_name] = output
            else:
                features[output_name] = output

        return features, labels

    # Merge dictionaries for passing to the model function
    metadata = data_loader.get_metadata()

    params = {
            'model': {**model_hyperparameters, **metadata},
            'training': {**training_hyperparameters, **metadata}
            }

    # Define model function with model, mode (train/predict),
    # metrics, optimizer, learning rate, etc.
    # to pass into TF Estimator
    def model_fn(features, labels, mode, params, config):
        
        training = True if mode == tf.estimator.ModeKeys.TRAIN else False
       
        logits = model(features, params['model'], training)
        
        # Collect predictions
        predicted_classes = tf.cast(tf.argmax(logits, axis=1), tf.int32,
                name="predicted_classes")
        predictions = {
                'predicted_class': predicted_classes,
                'classifier_values': tf.nn.softmax(logits)
                }
        
        # For predict mode, we're done
        if mode == tf.estimator.ModeKeys.PREDICT:
            return tf.estimator.EstimatorSpec(
                    mode=mode,
                    predictions=predictions)

        training_params = params['training']

        # Compute class-weighted softmax-cross-entropy
        
        true_classes = tf.cast(labels['gamma_hadron_label'], tf.int32,
                name="true_classes")

        # Get class weights
        if training_params['apply_class_weights']:
            class_weights = tf.constant(training_params['class_weights'],
                    dtype=tf.float32, name="class_weights") 
            weights = tf.gather(class_weights, true_classes, name="weights")
        else:
            weights = 1.0

        onehot_labels = tf.one_hot(indices=true_classes,
                depth=training_params['num_classes'])

        # compute cross-entropy loss
        loss = tf.losses.softmax_cross_entropy(onehot_labels=onehot_labels, 
            logits=logits,weights=weights)
    
        # add regularization loss
        regularization_losses = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
        loss = tf.add_n([loss] + regularization_losses, name="loss")

        # Compute accuracy
        training_accuracy = tf.reduce_mean(tf.cast(tf.equal(true_classes, 
            predicted_classes), tf.float32),name="training_accuracy")
        tf.summary.scalar("accuracy", training_accuracy)

        # Scale the learning rate so batches with fewer triggered
        # telescopes don't have smaller gradients
        # Only apply learning rate scaling for array-level models
        if (training_params['scale_learning_rate'] and
                model_type == 'array'):
            trigger_rate = tf.reduce_mean(tf.cast(
                features['telescope_triggers'], tf.float32),
                name="trigger_rate")
            trigger_rate = tf.maximum(trigger_rate, 0.1) # Avoid division by 0
            scaling_factor = tf.reciprocal(trigger_rate, name="scaling_factor")
            learning_rate = tf.multiply(scaling_factor, 
                training_params['base_learning_rate'], name="learning_rate")
        else:
            learning_rate = training_params['base_learning_rate']
        
        # Select optimizer with appropriate arguments

        # Dict of optimizer_name: (optimizer_fn, optimizer_args)
        optimizers = {
                'Adadelta': (tf.train.AdadeltaOptimizer,
                    dict(learning_rate=learning_rate)),
                'Adam': (tf.train.AdamOptimizer,
                    dict(learning_rate=learning_rate,
                        epsilon=training_params['adam_epsilon'])),
                'RMSProp': (tf.train.RMSPropOptimizer,
                    dict(learning_rate=learning_rate)),
                'SGD': (tf.train.GradientDescentOptimizer,
                    dict(learning_rate=learning_rate))
                }

        optimizer_fn, optimizer_args = optimizers[training_params['optimizer']]
        optimizer = optimizer_fn(**optimizer_args)
    
        var_list = None
        if training_params['variables_to_train']:
            var_list = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES,
                    training_params['variables_to_train'])
       
        # Define train op with update ops dependency for batch norm
        update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        with tf.control_dependencies(update_ops):
            train_op = optimizer.minimize(loss,
                    global_step=tf.train.get_global_step(),
                    var_list=var_list)
        
        # Define the evaluation metrics
        eval_metric_ops = {
                'accuracy': tf.metrics.accuracy(true_classes, 
                    predicted_classes),
                'auc': tf.metrics.auc(true_classes, predicted_classes)
                }
        
        # add class-wise accuracies
        for i in range(training_params['num_classes']):
            weights = tf.cast(tf.equal(true_classes,tf.constant(i)),tf.int32)
            eval_metric_ops['accuracy_{}'.format(
                training_params['class_to_name'][i])] = tf.metrics.accuracy(
                        true_classes, predicted_classes, weights=weights)

        return tf.estimator.EstimatorSpec(
                mode=mode,
                loss=loss,
                train_op=train_op,
                eval_metric_ops=eval_metric_ops)

    # Log information on number of training and validation events, or test
    # events, depending on the mode
    logger.info("Batch size: {}".format(data_input_settings['batch_size']))
    if mode == 'train':
        num_training_events = len(list(training_generator()))
        num_validation_events = len(list(validation_generator()))
        logger.info("Training and evaluating...")
        logger.info("Total number of training events: {}".format(
            num_training_events))
        logger.info("Total number of validation events: {}".format(
            num_validation_events))
        logger.info("Number of training steps per epoch: {}".format(int(
            num_training_events/data_input_settings['batch_size'])))
        logger.info("Number of training steps per validation: {}".format(
            num_training_steps_per_validation))
    elif mode == 'predict':
        num_test_events = len(list(test_generator()))
        logger.info("Predicting...")
        logger.info("Total number of test events: {}".format(num_test_events))
    
    estimator = tf.estimator.Estimator(
            model_fn, 
            model_dir=model_dir, 
            params=params)

    hooks = None
    # Activate Tensorflow debugger if appropriate option set
    if run_tfdbg:
        if not isinstance(hooks, list):
            hooks = []
        hooks.append(tf_debug.LocalCLIDebugHook())

    if mode == 'train':
        # Train and evaluate the model
        num_epochs_remaining = num_epochs
        while train_forever or num_epochs_remaining:
            estimator.train(
                    lambda: input_fn(training_generator, data_input_settings),
                    steps=num_training_steps_per_validation, hooks=hooks)
            estimator.evaluate(
                    lambda: input_fn(validation_generator,
                        data_input_settings), hooks=hooks, name='validation')
            if not train_forever:
                num_epochs_remaining -= 1
    elif mode == 'predict':
        # Generate predictions
        predictions = estimator.predict(
                lambda: input_fn(test_generator, data_input_settings),
                hooks=hooks)

        # Get true labels if available
        true_labels = None
        if true_labels_given:
            true_labels = []
            features, labels = input_fn(test_generator, data_input_settings)
            with tf.Session() as sess:
                while True:
                    try:
                        batch_labels = sess.run(labels['gamma_hadron_label'])
                        true_labels.extend(batch_labels)
                    except tf.errors.OutOfRangeError:
                        break

        def write_predictions(file_handle, predictions, true_labels):
            if true_labels is not None:
                file_handle.write("predicted_class, true_class, classifier_value_0, classifier_value_1\n")
                for prediction, true_class in zip(predictions, true_labels):
                    predicted_class = prediction['predicted_class']
                    classifier_value_0 = prediction['classifier_values'][0]
                    classifier_value_1 = prediction['classifier_values'][1]
                    file_handle.write("{}, {}, {}, {}\n".format(
                        predicted_class, true_class, classifier_value_0,
                        classifier_value_1))
            else:
                file_handle.write("predicted_class, classifier_value_0, classifier_value_1\n")
                for prediction in predictions:
                    predicted_class = prediction['predicted_class']
                    classifier_value_0 = prediction['classifier_values'][0]
                    classifier_value_1 = prediction['classifier_values'][1]
                    file_handle.write("{}, {}, {}\n".format(predicted_class,
                        classifier_value_0, classifier_value_1))

        # Write predictions to a csv file
        if export_prediction_file:
            with open(prediction_path, 'w') as predict_file:
                write_predictions(predict_file, predictions, true_labels)
        else:
            write_predictions(sys.stdout, predictions, true_labels)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
            description=("Train/Predict with a ctalearn model."))
    parser.add_argument(
            '--mode',
            help="Mode to run in (train/predict)")
    parser.add_argument(
            'config_file',
            help="path to configobj configuration file with training options")
    parser.add_argument(
            '--config_spec_file',
            default='../config/configspec.ini',
            help="path to configobj configspec file to validate configuration options")
    parser.add_argument(
            '--debug',
            action='store_true',
            help="print debug/logger messages")
    parser.add_argument(
            '--log_to_file',
            action='store_true',
            help="log to a file in model directory instead of terminal")

    args = parser.parse_args()
   
    # Load configuration file
    validator = Validator()
    configspec = ConfigObj(args.config_spec_file, encoding='UTF8', list_values=False, _inspec=True)
    config = ConfigObj(args.config_file, configspec=configspec)
   
    # Validate config and print errors if any occurred
    # Error printing code based from example at
    # https://configobj.readthedocs.io/en/latest/configobj.html#validation
    result = config.validate(validator, preserve_errors=True)
    if result is True:
        run_model(config, mode=args.mode, debug=args.debug, log_to_file=args.log_to_file)
    else:
        for entry in flatten_errors(config, result):
            # each entry is a tuple
            section_list, key, error = entry
            if key is not None:
                section_list.append(key)
            else:
                section_list.append('[missing section]')
            section_string = ', '.join(section_list)
            if error == False:
                error = 'Missing value or section.'
            print(section_string, ' = ', error)

