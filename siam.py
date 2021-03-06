from __future__ import division, print_function

import os
import threading
import importlib

import numpy as np

# from src.model.caps_merge import generate_model
# from src.model.cnn_merge import generate_model
from src.train import train_model
from src.test import cmc, test
from src.generator import ReidGenerator, testGenerator, featureGenerator
from src.utils.log import log
import src.utils.plot as plot

class ReID:
    """docstring for ReID."""
    def __init__(self, model_data, b_no_ui=False):
        self.model_data = model_data

        self.reid_network = None

        self.feature_network = None

        self.b_no_ui = b_no_ui

        self.__initEnv()
        self.__parseData()
        self.__generateNetwork()


    def run(self,
            b_load_weights=False,
            b_pretrain_model=False,
            b_train_model=False,
            b_test_model=False,
            b_lc=False):

        if b_lc:
            self.learningCurve()

        if b_load_weights:
            self.loadWeights()

        # Train
        pretrain = False
        if b_pretrain_model:
            self.pretrain_network()
            pretrain = True

        if b_train_model:
            self.train(pretrain)

        # Test
        if b_test_model:
            self.test()

        self.showPlot()

    def __initEnv(self):
        # Disable tf debug
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

        # Choose GPU to use
        # os.environ["CUDA_VISIBLE_DEVICES"]="0"

    def __parseData(self):
        self.input_shape = self.model_data["input_shape"]
        self.dataset = self.model_data["dataset_path"]
        self.batch_size = self.model_data["batch_size"]
        self.steps_per_epoch = self.model_data["steps_per_epoch"]
        self.epochs = self.model_data["epochs"]
        self.validation_steps = self.model_data["validation_steps"]
        self.weights_file = self.model_data["weights_file"]
        self.model_name = self.model_data["model_name"]
        self.lr = self.model_data["lr"]

    def __generateNetwork(self):
        modellib = importlib.import_module("src.model." + self.model_name)
        self.reid_network = modellib.generate_model(input_shape=self.input_shape, lr=self.lr, feature=False)

        log("Model generated")

    def showPlot(self):
        if not self.b_no_ui:
            plot.showPlot()


    def pretrain_network(self):

        modellib = importlib.import_module("src.model." + self.model_name)
        reid_network, feature_network = modellib.generate_model(input_shape=self.input_shape, lr=self.lr, feature=True)

        generator_train = featureGenerator(
                            database=self.dataset,
                            batch_size=self.batch_size,
                            flag="train" )
        generator_val = featureGenerator(
                            database=self.dataset,
                            batch_size=self.batch_size,
                            flag="validation" )

        log("Training [features]")
        train_model(feature_network,
                    generator_train=generator_train,
                    generator_val=generator_train,
                    batch_size=self.batch_size,
                    steps_per_epoch=self.steps_per_epoch,
                    epochs=self.epochs,
                    validation_steps=self.validation_steps,
                    plot_title="loss [feature training]")

        reid_network.save_weights("pretrain.h5")

    def train(self, pretrain=False):
        if pretrain:
            self.reid_network.load_weights("pretrain.h5")
            log("Loaded pretrain weights")

        generator_train = ReidGenerator(
                            database=self.dataset,
                            batch_size=self.batch_size,
                            flag="train",
                            p=0.33)
        generator_val = ReidGenerator(
                            database=self.dataset,
                            batch_size=self.batch_size,
                            flag="validation")

        log("Training [reid]")
        train_model(self.reid_network,
                    generator_train=generator_train,
                    generator_val=generator_val,
                    batch_size=self.batch_size,
                    steps_per_epoch=self.steps_per_epoch,
                    epochs=self.epochs,
                    validation_steps=self.validation_steps,
                    plot_title="loss [reid training]")

    def test(self):
        generator_test = testGenerator(database=self.dataset)

        log("Testing model [cmc]")
        cmc(self.reid_network, generator_test, self.b_no_ui)

    def loadWeights(self):
        self.reid_network.load_weights(os.path.join("weights", self.weights_file))
        log("Loaded weights")

    def learningCurve(self, n_from=1, n_to=4, n_steps=1):
        log("Begining learning curve")
        self.reid_network.load_weights("weights/feature.hdf5")
        # if self.pretrain:
        #     self.train(flag="feature")
        # self.reid_network.save_weights("weights/feature.hdf5")
        Wsave = self.reid_network.get_weights()

        plot_loss = []
        plot_val_loss = []

        generator_val = ReidGenerator(
                            database=self.dataset,
                            batch_size=self.batch_size*10,
                            flag="validation")
        batch_val = next(generator_val)

        for n_examples in range(n_from, n_to, n_steps):
            log("\tTraining with {} batchs".format(n_examples))
            self.reid_network.set_weights(Wsave)

            # Trains on n examples
            batch_train = next(ReidGenerator(
                                database=self.dataset,
                                batch_size=n_examples,
                                flag="train"))
            self.reid_network.fit(x=batch_train[0],
                                    y=batch_train[1],
                                    batch_size=self.batch_size,
                                    epochs=3,
                                    verbose=1)

            # Evaluate on these examples
            rslt = self.reid_network.evaluate(x=batch_train[0],
                                                y=batch_train[1],
                                                batch_size=self.batch_size,
                                                verbose=1)
            plot_loss.append( rslt[1] )

            # Evaluate on all CV set
            rslt = self.reid_network.evaluate(x=batch_val[0],
                                                y=batch_val[1],
                                                batch_size=self.batch_size,
                                                verbose=1)
            plot_val_loss.append( rslt[1] )

        print(*plot_loss, sep="; ")
        print(*plot_val_loss, sep="; ")
        plot.learningCurve(plot_loss, plot_val_loss)
        plot.showPlot()
