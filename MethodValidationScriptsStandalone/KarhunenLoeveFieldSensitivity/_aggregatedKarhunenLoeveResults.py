__author__ = 'Kristof Attila S.'
__version__ = '0.1'
__date__  = '17.09.20'

__all__ = ['AggregatedKarhunenLoeveResults']

import openturns as ot
import uuid
from collections import Sequence, Iterable
from copy import copy, deepcopy

def all_same(items):
    #Checks if all items of a list are the same
    return all(x == items[0] for x in items)

def atLeastList(elem):
    if isinstance(elem, Iterable) :
        return list(elem)
    else :
        return [elem]

def addConstant2Iterable(obj, constant):
    if isinstance(obj, ot.ProcessSample):
        for k in range(obj.getSize()):
            obj[k] += constant
    if isinstance(obj, ot.Field):
        vals = obj.getValues()
        vals += constant
        obj.setValues(vals)
    if isinstance(obj, ot.Point):
        for i in range(obj.getSize):
            obj[i] += constant
    if isinstance(obj, ot.Sample):
        for i in range(obj.getSize()):
            for j in range(obj.getDimension()):
                obj[i,j] += constant


class AggregatedKarhunenLoeveResults(object):  ### ComposedKLResultsAndDistributions ##########
    '''Function being a buffer between the processes and the sensitivity
    Analysis
    '''
    def __init__(self, composedKLResultsAndDistributions):
        self.__KLResultsAndDistributions__ = atLeastList(composedKLResultsAndDistributions) #KLRL : Karhunen Loeve Result List
        assert len(self.__KLResultsAndDistributions__)>0
        self.__field_distribution_count__ = len(self.__KLResultsAndDistributions__)
        self.__name__ = 'Unnamed'
        self.__KL_lifting__ = []
        self.__KL_projecting__ = []

        #Flags
        self.__isProcess__ = [False]*self.__field_distribution_count__
        self.__has_distributions__ = False
        self.__unified_dimension__ = False
        self.__unified_mesh__ = False
        self.__isAggregated__ = False
        self.__means__ = [.0]*self.__field_distribution_count__
        self.__liftWithMean__ = False

        # checking the nature of eachelement of the input list
        for i in range(self.__field_distribution_count__):
            # If element is a Karhunen Loeve decomposition
            if isinstance(self.__KLResultsAndDistributions__[i], ot.KarhunenLoeveResult):
                # initializing lifting and projecting objects.
                self.__KL_lifting__.append(ot.KarhunenLoeveLifting(self.__KLResultsAndDistributions__[i]))
                self.__KL_projecting__.append(ot.KarhunenLoeveProjection(self.__KLResultsAndDistributions__[i]))
                self.__isProcess__[i] = True

            # If element is a distribution
            elif isinstance(self.__KLResultsAndDistributions__[i], (ot.Distribution, ot.DistributionImplementation)):
                self.__has_distributions__ = True
                if self.__KLResultsAndDistributions__[i].getMean()[0] != 0 :
                    print('The mean value of distribution at index {} of type {} is not 0.'.format(str(i), self.__KLResultsAndDistributions__[i].getClassName()))
                    self.__means__[i] = self.__KLResultsAndDistributions__[i].getMean()[0]
                    self.__KLResultsAndDistributions__[i] -= self.__means__[i]
                    print('Distribution recentered and mean added to list of means')
                    print('Set the "liftWithMean" flag to true if you want to include the mean.')
                # We can say that the inverse iso probabilistic transformation is analoguous to lifting
                self.__KL_lifting__.append(self.__KLResultsAndDistributions__[i].getInverseIsoProbabilisticTransformation())
                # We can say that the iso probabilistic transformation is analoguous to projecting
                self.__KL_projecting__.append(self.__KLResultsAndDistributions__[i].getIsoProbabilisticTransformation())

        # If the function has distributions it cant be homogenous
        if not self.__has_distributions__ :
            self.__unified_mesh__ = all_same([self.__KLResultsAndDistributions__[i].getMesh() for i in range(self.__field_distribution_count__)])
            self.__unified_dimension__ = (   all_same([self.__KLResultsAndDistributions__[i].getCovarianceModel().getOutputDimension() for i in range(self.__field_distribution_count__)])\
                                         and all_same([self.__KLResultsAndDistributions__[i].getCovarianceModel().getInputDimension() for i in range(self.__field_distribution_count__)]))

        # If only one object is passed it has to be an decomposed aggregated process
        if self.__field_distribution_count__ == 1 :
            if hasattr(self.__KLResultsAndDistributions__[0], 'getCovarianceModel') and hasattr(self.__KLResultsAndDistributions__[0], 'getMesh'):
                #Cause when aggregated there is usage of multvariate covariance functions
                self.__isAggregated__ = self.__KLResultsAndDistributions__[0].getCovarianceModel().getOutputDimension() > self.__KLResultsAndDistributions__[0].getMesh().getDimension()
                print('Process seems to be aggregated. ')
            else :
                print('There is no point in passing only one process that is not aggregated')
                raise TypeError

        self.threshold = max([self.__KLResultsAndDistributions__[i].getThreshold() if hasattr(self.__KLResultsAndDistributions__[i], 'getThreshold') else 1e-3 for i in range(self.__field_distribution_count__)])
        #Now we gonna get the data we will usually need
        self.__process_distribution_description__ = [self.__KLResultsAndDistributions__[i].getName() for i in range(self.__field_distribution_count__)]
        self._checkSubNames()
        self.__mode_count__ = [self.__KLResultsAndDistributions__[i].getEigenValues().getSize() if hasattr(self.__KLResultsAndDistributions__[i], 'getEigenValues') else 1 for i in range(self.__field_distribution_count__)]
        self.__mode_description__ = self._getModeDescription()

    def __repr__(self):
        covarianceList = self.getCovarianceModel()
        eigValList = self.getEigenValues()
        meshList = self.getMesh()
        reprStr = '| '.join(['class = ComposedKarhunenLoeveResultsAndDistributions',
                             'name = {}'.format(self.getName()),
                            'Aggregation Order = {}'.format(str(self.__field_distribution_count__)),
                            'Threshold = {}'.format(str(self.threshold)),
                            *['Covariance Model {} = '.format(str(i))+covarianceList[i].__repr__() for i in range(self.__field_distribution_count__)],
                            *['Eigen Value {} = '.format(str(i))+eigValList[i].__repr__() for i in range(self.__field_distribution_count__)],
                            *['Mesh {} = '.format(str(i))+meshList[i].__repr__().partition('data=')[0] for i in range(self.__field_distribution_count__)]])
        return reprStr


    def _checkSubNames(self):
        '''Here we're gonna see if all the names are unique, so there can be
        no confusion. We could also check ID's'''
        if len(set(self.__process_distribution_description__)) != len(self.__process_distribution_description__) :
            print('The process names are not unique.')
            print('Using generic name. ')
            for i, process in enumerate(self.__KLResultsAndDistributions__):
                oldName = process.getName()
                newName = 'X_'+str(i)
                print('Old name was {}, new one is {}'.format(oldName, newName))
                process.setName(newName)
            self.__process_distribution_description__ = [self.__KLResultsAndDistributions__[i].getName() for i in range(self.__field_distribution_count__)]

    def _getModeDescription(self):
        modeDescription = list()
        for i, nMode in enumerate(self.__mode_count__):
            for j in range(nMode):
                modeDescription.append(self.__process_distribution_description__[i]+'_'+str(j))
        return modeDescription

    def _checkCoefficients(self, coefficients):
        '''Function to check if the vector passed has the right number of
        elements'''
        nModes = sum(self.__mode_count__)
        if (isinstance(coefficients, ot.Point), len(coefficients) == nModes):
            return True
        elif (isinstance(coefficients, (ot.Sample, ot.SampleImplementation)) and len(coefficients[0]) == nModes):
            return True
        else :
            print('The vector passed has not the right number of elements.')
            print('n° elems: {} != {}'.format(str(len(coefficients)), str(nModes)))
            return False

    # new method
    def getMean(self, i = None):
        if i is not None:
            return self.__means__[i]
        else :
            return self.__means__

    # new method
    def setMean(self, i, val ):
        self.__means__[i] = val

    # new method
    def setLiftWithMean(self, theBool):
        self.__liftWithMean__ = theBool

    def getClassName(self):
        '''returns list of class names
        '''
        classNames=[self.__KLResultsAndDistributions__[i].__class__.__name__ for i in range(self.__field_distribution_count__) ]
        return list(set(classNames))

    def getCovarianceModel(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getCovarianceModel() if hasattr(self.__KLResultsAndDistributions__[i], 'getCovarianceModel') else None for i in range(self.__field_distribution_count__) ]

    def getEigenValues(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getEigenValues() if hasattr(self.__KLResultsAndDistributions__[i], 'getEigenValues') else None for i in range(self.__field_distribution_count__) ]

    def getId(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getId() for i in range(self.__field_distribution_count__) ]

    def getImplementation(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getImplementation() if hasattr(self.__KLResultsAndDistributions__[i], 'getImplementation') else None for i in range(self.__field_distribution_count__) ]

    def getMesh(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getMesh() if hasattr(self.__KLResultsAndDistributions__[i], 'getMesh') else None for i in range(self.__field_distribution_count__) ]

    def getModes(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getModes() if hasattr(self.__KLResultsAndDistributions__[i], 'getModes') else None for i in range(self.__field_distribution_count__) ]

    def getModesAsProcessSample(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getModesAsProcessSample() if hasattr(self.__KLResultsAndDistributions__[i], 'getModesAsProcessSample') else None for i in range(self.__field_distribution_count__) ]

    def getName(self):
        return self.__name__

    def getProjectionMatrix(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getProjectionMatrix() if hasattr(self.__KLResultsAndDistributions__[i], 'getProjectionMatrix') else None for i in range(self.__field_distribution_count__) ]

    def getScaledModes(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getScaledModes() if hasattr(self.__KLResultsAndDistributions__[i], 'getScaledModes') else None for i in range(self.__field_distribution_count__) ]

    def getScaledModesAsProcessSample(self):
        '''
        '''
        return [self.__KLResultsAndDistributions__[i].getScaledModesAsProcessSample() if hasattr(self.__KLResultsAndDistributions__[i], 'getScaledModes') else None for i in range(self.__field_distribution_count__) ]

    def getThreshold(self):
        '''
        '''
        return self.threshold

    def setName(self,name):
        self.__name__ = name

    def liftAsProcessSample(self, coefficients):
        '''Function to lift a sample of coefficients into a collections of
        process samples and points
        '''
        assert isinstance(coefficients, (ot.Sample, ot.SampleImplementation))
        print('Lifting as process sample')
        jumpDim = 0
        processes = []
        for i in range(self.__field_distribution_count__):
            if self.__isProcess__[i] :
                if not self.__liftWithMean__:
                    processes.append(self.__KL_lifting__[i](coefficients[:, jumpDim : jumpDim + self.__mode_count__[i]]))
                else :
                    processSample = self.__KL_lifting__[i](coefficients[:, jumpDim : jumpDim + self.__mode_count__[i]])
                    addConstant2Iterable(processSample, self.__means__[i])
                    processes.append(processSample)
            else :
                if not self.__liftWithMean__:
                    processSample = ot.ProcessSample(ot.Mesh(), 0, 1)
                    val_sample = self.__KL_lifting__[i](coefficients[:, jumpDim : jumpDim + self.__mode_count__[i]])
                    for j, value in enumerate(val_sample):
                        field = ot.Field(ot.Mesh(),1)
                        field.setValueAtIndex(0,value)
                        processSample.add(field)
                    processes.append(processSample)
                else :
                    processSample = ot.ProcessSample(ot.Mesh(), 0, 1)
                    val_sample = self.__KL_lifting__[i](coefficients[:, jumpDim : jumpDim + self.__mode_count__[i]])
                    mean = self.__means__[i]
                    for j, value in enumerate(val_sample):
                        field = ot.Field(ot.Mesh(),1)
                        field.setValueAtIndex(0,[value[0]+mean]) # adding mean
                        processSample.add(field)
                    processes.append(processSample)
            jumpDim += self.__mode_count__[i]
        return processes

    def liftAsField(self, coefficients):
        '''function lifting a vector of coefficients into a field.
        '''
        assert isinstance(coefficients, (ot.Point)), 'function only lifts points'
        valid = self._checkCoefficients(coefficients)
        print('Lifting as field')
        if valid :
            to_return = []
            jumpDim = 0
            for i in range(self.__field_distribution_count__):
                if self.__isProcess__[i] :
                    field = self.__KLResultsAndDistributions__[i].liftAsField(coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                    jumpDim += self.__mode_count__[i]
                    if not self.__liftWithMean__:
                        to_return.append(field)
                    else :
                        vals = field.getValues()
                        vals += self.__means__[i]
                        field.setValues(vals)
                        to_return.append(field)
                else :
                    value = self.__KL_lifting__[i](coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                    jumpDim += self.__mode_count__[i]
                    if not self.__liftWithMean__:
                        #print('field value is',value)
                        field = ot.Field(ot.Mesh(),1)
                        field.setValueAtIndex(0,value)
                        to_return.append(field)
                    else :
                        #print('field value is',value)
                        field = ot.Field(ot.Mesh(),1)
                        value[0] += self.__means__[i]
                        field.setValueAtIndex(0,value)
                        to_return.append(field)
            return to_return
        else :
            raise Exception('DimensionError : the vector of coefficient has the wrong shape')

    def liftAsSample(self, coefficients):
        ''' function to lift into a list of samples a Point of coefficents
        '''
        assert isinstance(coefficients, ot.Point)
        print('Lifting as sample')
        valid = self._checkCoefficients(coefficients)
        modes = self.__mode_count__
        jumpDim = 0
        if valid :
            if self.__isAggregated__ :
                if not self.__liftWithMean__ :
                    sample = self.__KLResultsAndDistributions__[0].liftAsSample(coefficients)
                    sample.setDescription(self.__mode_description__)
                    return sample
                else :
                    raise NotImplementedError
            else :
                to_return = []
                for i in range(self.__field_distribution_count__):
                    if self.__isProcess__[i] :
                        if not self.__liftWithMean__ :
                            sample = self.__KLResultsAndDistributions__[i].liftAsSample(coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                            to_return.append(sample)
                        else :
                            sample = self.__KLResultsAndDistributions__[i].liftAsSample(coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                            sample += self.__means__[i]
                            to_return.append(sample)
                    else :
                        if not self.__liftWithMean__ :
                            value = self.__KL_lifting__[i](coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                            sample = ot.Sample([value])
                            to_return.append(sample)
                        else :
                            value = self.__KL_lifting__[i](coefficients[jumpDim : jumpDim + self.__mode_count__[i]])
                            value[0] += self.__means__[i]
                            sample = ot.Sample([value])
                            to_return.append(sample)
                    jumpDim += self.__mode_count__[i]
                return to_return
        else :
            raise Exception('DimensionError : the vector of coefficient has the wrong shape')

    def project(self, args):
        '''Project a function or a field on the eigenmodes basis. As the eigenmode basis is constructed over
        the decomposition of centered processes and iso probabilstic transformations of centered scalar
        distributions, objects that are to projected have to be centered first!
        '''
        args = atLeastList(args)
        nArgs = len(args)
        nProcess = self.__field_distribution_count__
        isAggreg = self.__isAggregated__
        homogenMesh = self.__unified_mesh__
        homogenDim = self.__unified_dimension__
        assert isinstance(args[0], (ot.Field, ot.Sample, ot.ProcessSample,
                                    ot.AggregatedFunction,
                                    ot.SampleImplementation))
        for i in range(nArgs):
            addConstant2Iterable(args[i],-1*self.__means__[i]) # We then subtract the mean of each process to any entry, so we are again in the centered case

        if isAggreg :
            print('projection of aggregated process')
            assert nProcess==1, 'do not work with lists of aggregated processes'
            assert homogenMesh, 'if aggregated then the mesh is shared'
            assert homogenDim, 'if aggregated then the dimension is shared'
            inDim = self.__KLResultsAndDistributions__[0].getCovarianceModel().getInputDimension()
            outDim = self.__KLResultsAndDistributions__[0].getCovarianceModel().getOutputDimension()
            if isinstance(args[0], (ot.Field, ot.ProcessSample, ot.AggregatedFunction)):
                try : fdi = args[0].getInputDimension()
                except : fdi = args[0].getMesh().getDimension()
                try : fdo = args[0].getOutputDimension()
                except : fdo = args[0].getDimension()

                if fdi == inDim and fdo == outDim :
                    if nArgs > 1 and not isinstance(args[0], ot.ProcessSample):
                        sample = ot.Sample([self.__KL_projecting__[0](args[i]) for i in range(nArgs)])
                        sample.setDescription(self.__mode_description__)
                        return sample
                    elif isinstance(args[0], ot.Field) :
                        projection = self.__KL_projecting__[0](args[0])
                        projDescription = list(zip(self.__mode_description__, projection))
                        projection = ot.PointWithDescription(projDescription)
                        return projection
                    elif isinstance(args[0], ot.ProcessSample):
                        projection = self.__KL_projecting__[0](args[0])
                        projection.setDescription(self.__mode_description__)
                        return projection
                else :
                    raise Exception('InvalidDimensionException')

        else :
            if isinstance(args[0], (ot.Field, ot.Sample)):
                print('projection of a list of {} '.format(', '.join([args[i].__class__.__name__ for i in range(nArgs)])))
                assert nArgs==nProcess, 'Pass a list of same length then aggregation order'
                try:
                    projection =list()
                    for i in range(nProcess):
                        if isinstance(args[i], (ot.Sample, ot.Field)) and self.__isProcess__[i]:
                            projection.append(list(self.__KLResultsAndDistributions__[i].project(args[i])))
                        else :
                            ELEM = list(self.__KL_projecting__[i](args[i]))
                            projection.append(ELEM)
                    # this comprehensive list transforms a list[list[float], ot.Point] into a flat list of floats
                    projectionFlat = [item if not isinstance(item,(ot.Point)) else item[0] for sublist in projection for item in sublist]
                    output = ot.PointWithDescription(list(zip(self.__mode_description__, projectionFlat)))
                    return output
                except Exception as e :
                    raise e

            elif isinstance(args[0], ot.ProcessSample):
                print('projection of a list of {} '.format(', '.join([args[i].__class__.__name__ for i in range(nArgs)])))
                assert nArgs==nProcess, 'Pass a list of same length then aggregation order'
                try:
                    projectionSample = ot.Sample(0,sum(self.__mode_count__))
                    sampleSize = args[0].getSize()
                    #print('Process args are:',args)
                    projList = []
                    for idx in range(nProcess):
                        if self.__isProcess__[idx]:
                            projList.append(self.__KL_projecting__[idx](args[idx]))
                        else:
                            distributionSample = ot.Sample([args[idx][i][0] for i in range(args[idx].getSize())])
                            projList.append(self.__KL_projecting__[idx](distributionSample))

                    for idx in range(sampleSize):
                        l = [list(projList[j][idx]) for j in range(nProcess)]
                        projectionSample.add(
                            [item for sublist in l for item in sublist])
                    projectionSample.setDescription(self.__mode_description__)
                    return projectionSample
                except Exception as e:
                    raise e

    def getAggregationOrder(self):
        return self.__field_distribution_count__

    def getSizeModes(self):
        return sum(self.__mode_count__)








##    def lift(self, coefficients):  ### NOT SURE IF NEDDED
##        '''lift a point into a list of functions  ### NOT SURE IF NEDDED
##        '''  ### NOT SURE IF NEDDED
##        assert isinstance(coefficients, (ot.Point)), 'function only lifts points'  ### NOT SURE IF NEDDED
##        valid = self._checkCoefficients(coefficients)  ### NOT SURE IF NEDDED
##        modes = copy(self.__mode_count__)  ### NOT SURE IF NEDDED
##        if valid :  ### NOT SURE IF NEDDED
##            to_return = []  ### NOT SURE IF NEDDED
##            for i in range(self.__field_distribution_count__):  ### NOT SURE IF NEDDED
##                if self.__isProcess__[i] :  ### NOT SURE IF NEDDED
##                    if not self.__liftWithMean__:  ### NOT SURE IF NEDDED
##                        to_return.append(self.__KLResultsAndDistributions__[i].lift(coefficients[i*modes[i]:(i+1)*modes[i]]))  ### NOT SURE IF NEDDED
##                    else :  ### NOT SURE IF NEDDED
##                        function = self.__KLResultsAndDistributions__[i].lift(coefficients[i*modes[i]:(i+1)*modes[i]])  ### NOT SURE IF NEDDED
##                        cst_func = ot.SymbolicFunction(ot.Description_BuildDefault(function.getInputDimension(),'X'),[str(self.__means__[i])])  ### NOT SURE IF NEDDED
##                        out_func = ot.LinearCombinationFunction([function,cst_func],[1,1])  ### NOT SURE IF NEDDED
##                        to_return.append(out_func)  ### NOT SURE IF NEDDED
##                else :  ### NOT SURE IF NEDDED
##                    if not self.__liftWithMean__:  ### NOT SURE IF NEDDED
##                        # it is not a process so only scalar distribution, centered  ### NOT SURE IF NEDDED
##                        const = self.__KL_lifting__[i](coefficients[i*modes[i]:(i+1)*modes[i]])  ### NOT SURE IF NEDDED
##                        # make dummy class.  ### NOT SURE IF NEDDED
##                        class constFunc :  ### NOT SURE IF NEDDED
##                            def __init__(self,x):  ### NOT SURE IF NEDDED
##                                self.x = x  ### NOT SURE IF NEDDED
##                            def __call__(self,*args):  ### NOT SURE IF NEDDED
##                                return self.x  ### NOT SURE IF NEDDED
##                        func = constFunc(const)  ### NOT SURE IF NEDDED
##                        to_return.append(func)  ### NOT SURE IF NEDDED
##                    else :  ### NOT SURE IF NEDDED
##                        const = self.__KL_lifting__[i](coefficients[i*modes[i]:(i+1)*modes[i]])  ### NOT SURE IF NEDDED
##                        # make dummy class.  ### NOT SURE IF NEDDED
##                        class constFunc :  ### NOT SURE IF NEDDED
##                            def __init__(self,x):  ### NOT SURE IF NEDDED
##                                self.x = x  ### NOT SURE IF NEDDED
##                            def __call__(self,*args):  ### NOT SURE IF NEDDED
##                                return self.x  ### NOT SURE IF NEDDED
##                        func = constFunc(const+self.__means__[i])  ### NOT SURE IF NEDDED
##                        to_return.append(func)  ### NOT SURE IF NEDDED
##            return to_return  ### NOT SURE IF NEDDED
##        else :  ### NOT SURE IF NEDDED
##            raise Exception('DimensionError : the vector of coefficient has the wrong shape')  ### NOT SURE IF NEDDED
