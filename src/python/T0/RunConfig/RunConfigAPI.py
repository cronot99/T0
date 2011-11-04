"""
_RunConfigAPI_

API for anyting RunConfig related

"""
import logging
import threading

from WMCore.DAOFactory import DAOFactory

from T0.RunConfig import ConfDB
from T0.RunConfig.Tier0Config import retrieveDatasetConfig
from T0.RunConfig.Tier0Config import addRepackConfig
from T0.RunConfig.Tier0Config import deleteStreamConfig


def configureRun(tier0Config, run, referenceHltConfig = None):
    """
    _configureRun_

    Called by Tier0Feeder for new runs.

    Retrieve HLT config and configure global run
    settings and stream/dataset/trigger mapping

    """
    logging.debug("configureRun() : %d" % run)
    myThread = threading.currentThread()

    daoFactory = DAOFactory(package = "T0.WMBS",
                            logger = myThread.logger,
                            dbinterface = myThread.dbi)

    getHLTKeyForRunDAO = daoFactory(classname = "RunConfig.GetHLTKeyForRun")
    hltkey = getHLTKeyForRunDAO.execute(run, transaction = False)

    logging.debug("HLT key: %s" % hltkey)

    #
    # treat centralDAQ or miniDAQ runs (have an HLT key) different from local runs
    #
    if hltkey != None:

        hltConfig = ConfDB.getConfiguration(hltkey)
        if hltConfig == None:
            # workaround to make unit test work outside CERN
            if referenceHltConfig != None:
                hltConfig = referenceHltConfig
            else:
                raise RuntimeError, "Could not retrieve HLT config for run %d" % run

        # update global run settings
        updateRunDAQ = daoFactory(classname = "RunConfig.UpdateRun")

        # write stream/dataset/trigger mapping
        insertStreamDAO = daoFactory(classname = "RunConfig.InsertStream")
        insertDatasetDAO = daoFactory(classname = "RunConfig.InsertPrimaryDataset")
        insertStreamDatasetDAO = daoFactory(classname = "RunConfig.InsertStreamDataset")
        insertTriggerDAO = daoFactory(classname = "RunConfig.InsertTrigger")
        insertDatasetTriggerDAO = daoFactory(classname = "RunConfig.InsertDatasetTrigger")
        updateRunDAO = daoFactory(classname = "RunConfig.UpdateRun")

        bindsStream = []
        bindsDataset = []
        bindsStreamDataset = []
        bindsTrigger = []
        bindsDatasetTrigger = []
        for stream, datasetDict in hltConfig['mapping'].items():
            bindsStream.append( { 'STREAM' : stream } )
            for dataset, paths in datasetDict.items():
                bindsDataset.append( { 'PRIMDS' : dataset } )
                bindsStreamDataset.append( { 'RUN' : run,
                                             'PRIMDS' : dataset,
                                             'STREAM' : stream } )
                for path in paths:
                    bindsTrigger.append( { 'TRIG' : path } )
                    bindsDatasetTrigger.append( { 'RUN' : run,
                                                  'TRIG' : path,
                                                  'PRIMDS' : dataset } )

        try:

            myThread.transaction.begin()

            updateRunDAO.execute(run, hltConfig['process'],
                                 tier0Config.Global.AcquisitionEra,
                                 tier0Config.Global.RecoTimeout,
                                 tier0Config.Global.RecoLockTimeout)
            insertStreamDAO.execute(bindsStream)
            insertDatasetDAO.execute(bindsDataset)
            insertStreamDatasetDAO.execute(bindsStreamDataset)
            insertTriggerDAO.execute(bindsTrigger)
            insertDatasetTriggerDAO.execute(bindsDatasetTrigger)

            myThread.transaction.commit()

        except Exception, e:

            myThread.transaction.rollback()
            raise

    else:

        # update global run settings
        updateRunDAO = daoFactory(classname = "RunConfig.UpdateRun")

        try:

            updateRunDAQ.execute(run, "FakeProcessName",
                                 "FakeAcquisitionEra",
                                 transaction = False)

        except Exception, e:

            myThread.transaction.rollback()
            raise

        return

def configureRunStream(tier0Config, run, stream):
    """
    _configureRunStream_

    Called by Tier0Feeder for new run/streams.

    Retrieve global run settings and build the part
    of the configuration relevant to run/stream
    and write it to the database.

    Create workflows, filesets and subscriptions for
    the processing of runs/streams.

    """
    logging.debug("configureRunStream() : %d , %s" % (run, stream))
    myThread = threading.currentThread()

    daoFactory = DAOFactory(package = "T0.WMBS",
                            logger = myThread.logger,
                            dbinterface = myThread.dbi)

    getHLTKeyForRunDAO = daoFactory(classname = "RunConfig.GetHLTKeyForRun")
    hltkey = getHLTKeyForRunDAO.execute(run, transaction = False)

    #
    # treat centralDAQ or miniDAQ runs (have an HLT key) different from local runs
    #
    if hltkey != None:

        # streams not explicitely configured are repacked
        if stream not in tier0Config.Streams.dictionary_().keys():
            addRepackConfig(tier0Config, stream)

        streamConfig = tier0Config.Streams.dictionary_()[stream]

        # write stream/dataset mapping (for special express and error datasets)
        insertDatasetDAO = daoFactory(classname = "RunConfig.InsertPrimaryDataset")
        insertStreamDatasetDAO = daoFactory(classname = "RunConfig.InsertStreamDataset")

        # write stream configuration
        insertStreamStyleDAO = daoFactory(classname = "RunConfig.InsertStreamStyle")
        insertRepackConfigDAO = daoFactory(classname = "RunConfig.InsertRepackConfig")
        insertExpressConfigDAO = daoFactory(classname = "RunConfig.InsertExpressConfig")
        insertSpecialDatasetDAO = daoFactory(classname = "RunConfig.InsertSpecialDataset")
        insertDatasetScenarioDAO = daoFactory(classname = "RunConfig.InsertDatasetScenario")
        insertCMSSWVersionDAO = daoFactory(classname = "RunConfig.InsertCMSSWVersion")
        updateStreamOverrideDAO = daoFactory(classname = "RunConfig.UpdateStreamOverride")
        insertErrorDatasetDAO = daoFactory(classname = "RunConfig.InsertErrorDataset")
        insertRecoConfigDAO = daoFactory(classname = "RunConfig.InsertRecoConfig")
        insertStorageNodeDAO = daoFactory(classname = "RunConfig.InsertStorageNode")
        insertPhEDExConfigDAO = daoFactory(classname = "RunConfig.InsertPhEDExConfig")
        insertPromptSkimConfigDAO = daoFactory(classname = "RunConfig.InsertPromptSkimConfig")

        bindsDataset = []
        bindsStreamDataset = []
        bindsStreamStyle = {'RUN' : run,
                            'STREAM' : stream,
                            'STYLE': streamConfig.ProcessingStyle }
        bindsRepackConfig = {}
        bindsExpressConfig = {}
        bindsSpecialDataset = {}
        bindsDatasetScenario = []
        bindsCMSSWVersion = []
        bindsStreamOverride = {}
        bindsErrorDataset = []
        bindsRecoConfig = []
        bindsStorageNode = []
        bindsPhEDExConfig = []
        bindsPromptSkimConfig = []

        #
        # first take care of all stream settings
        #
        if streamConfig.ProcessingStyle == "Bulk":

            bindsRepackConfig = { 'RUN' : run,
                                  'STREAM' : stream,
                                  'PROC_VER': streamConfig.Repack.ProcessingVersion }

        elif streamConfig.ProcessingStyle == "Express":

            writeSkims = None
            if len(streamConfig.Express.Producers) > 0:
                writeSkims = ",".join(streamConfig.Express.Producers)

            bindsExpressConfig = { 'RUN' : run,
                                   'STREAM' : stream,
                                   'PROC_VER' : streamConfig.Express.ProcessingVersion,
                                   'WRITE_TIERS' : ",".join(streamConfig.Express.DataTiers),
                                   'WRITE_SKIMS' : writeSkims,
                                   'GLOBAL_TAG' : streamConfig.Express.GlobalTag,
                                   'PROC_URL' : streamConfig.Express.ProcessingConfigURL,
                                   'MERGE_URL' : streamConfig.Express.AlcaMergeConfigURL }

            specialDataset = "Stream%s" % stream
            bindsDataset.append( { 'PRIMDS' : specialDataset } )
            bindsStreamDataset.append( { 'RUN' : run,
                                         'PRIMDS' : specialDataset,
                                         'STREAM' : stream } )
            bindsSpecialDataset = { 'STREAM' : stream,
                                    'PRIMDS' : specialDataset }
            bindsDatasetScenario.append( { 'RUN' : run,
                                           'PRIMDS' : specialDataset,
                                           'SCENARIO' : streamConfig.Express.Scenario } )

        getStreamOnlineVersionDAO = daoFactory(classname = "RunConfig.GetStreamOnlineVersion")
        onlineVersion = getStreamOnlineVersionDAO.execute(run, stream, transaction = False)

        overrideVersion = streamConfig.VersionOverride.get(onlineVersion, None)
        if overrideVersion != None:
            bindsCMSSWVersion.append( { 'VERSION' : overrideVersion } )
            bindsStreamOverride =  { "RUN" : run,
                                     "STREAM" : stream,
                                     "OVERRIDE" : overrideVersion }

        #
        # then configure datasets
        #
        getStreamDatasetsDAO = daoFactory(classname = "RunConfig.GetStreamDatasets")
        datasets = getStreamDatasetsDAO.execute(run, stream, transaction = False)

        for dataset in datasets:

            datasetConfig = retrieveDatasetConfig(tier0Config, dataset)

            if streamConfig.ProcessingStyle == "Bulk":

                bindsDatasetScenario.append( { 'RUN' : run,
                                               'PRIMDS' : datasetConfig.Name,
                                               'SCENARIO' : datasetConfig.Scenario } )

                errorDataset = "%s-%s" % (datasetConfig.Name, "Error")
                bindsDataset.append( { 'PRIMDS' : errorDataset } )
                bindsStreamDataset.append( { 'RUN' : run,
                                             'PRIMDS' : errorDataset,
                                             'STREAM' : stream } )
                bindsErrorDataset.append( { 'PARENT' : datasetConfig.Name,
                                            'ERROR' : errorDataset } )

                bindsDatasetScenario.append( { 'RUN' : run,
                                               'PRIMDS' : errorDataset,
                                               'SCENARIO' : datasetConfig.Scenario } )

                bindsCMSSWVersion.append( { 'VERSION' : datasetConfig.Reco.CMSSWVersion } )

                writeSkims = None
                if len(datasetConfig.Alca.Producers) > 0:
                    writeSkims = ",".join(datasetConfig.Alca.Producers)

                bindsRecoConfig.append( { 'RUN' : run,
                                          'PRIMDS' : datasetConfig.Name,
                                          'DO_RECO' : int(datasetConfig.Reco.DoReco),
                                          'CMSSW' : datasetConfig.Reco.CMSSWVersion,
                                          'RECO_SPLIT' : datasetConfig.Reco.EventSplit,
                                          'WRITE_RECO' : int(datasetConfig.Reco.WriteRECO),
                                          'WRITE_DQM' : int(datasetConfig.Reco.WriteDQM),
                                          'WRITE_AOD' : int(datasetConfig.Reco.WriteAOD),
                                          'PROC_VER' : datasetConfig.Reco.ProcessingVersion,
                                          'WRITE_SKIMS' : writeSkims,
                                          'GLOBAL_TAG' : datasetConfig.Reco.GlobalTag,
                                          'CONFIG_URL' : datasetConfig.Reco.ConfigURL } )

                bindsRecoConfig.append( { 'RUN' : run,
                                          'PRIMDS' : errorDataset,
                                          'DO_RECO' : int(False),
                                          'CMSSW' : datasetConfig.Reco.CMSSWVersion,
                                          'RECO_SPLIT' : datasetConfig.Reco.EventSplit,
                                          'WRITE_RECO' : int(datasetConfig.Reco.WriteRECO),
                                          'WRITE_DQM' : int(datasetConfig.Reco.WriteDQM),
                                          'WRITE_AOD' : int(datasetConfig.Reco.WriteAOD),
                                          'PROC_VER' : datasetConfig.Reco.ProcessingVersion,
                                          'WRITE_SKIMS' : writeSkims,
                                          'GLOBAL_TAG' : datasetConfig.Reco.GlobalTag,
                                          'CONFIG_URL' : datasetConfig.Reco.ConfigURL } )

                # leave out for now, might not be needed
                #insertAlcaConfig(dbConn, runNumber, datasetConfig)

                requestOnly = "y"
                if datasetConfig.CustodialAutoApprove:
                    requestOnly = "n"

                if datasetConfig.CustodialNode != None:

                    bindsStorageNode.append( { 'NODE' : datasetConfig.CustodialNode } )

                    bindsPhEDExConfig.append( { 'RUN' : run,
                                                'PRIMDS' : datasetConfig.Name,
                                                'NODE' : datasetConfig.CustodialNode,
                                                'CUSTODIAL' : 1,
                                                'REQ_ONLY' : requestOnly,
                                                'PRIO' : datasetConfig.CustodialPriority } )

                if datasetConfig.ArchivalNode != None:

                    bindsStorageNode.append( { 'NODE' : datasetConfig.ArchivalNode } )

                    bindsPhEDExConfig.append( { 'RUN' : run,
                                                'PRIMDS' : datasetConfig.Name,
                                                'NODE' : datasetConfig.ArchivalNode,
                                                'CUSTODIAL' : 0,
                                                'REQ_ONLY' : "n",
                                                'PRIO' : "high" } )
                
                    bindsPhEDExConfig.append( { 'RUN' : run,
                                                'PRIMDS' : errorDataset,
                                                'NODE' : datasetConfig.ArchivalNode,
                                                'CUSTODIAL' : 0,
                                                'REQ_ONLY' : "n",
                                                'PRIO' : "high" } )

                for tier1Skim in datasetConfig.Tier1Skims:

                    bindsCMSSWVersion.append( { 'VERSION' : tier1Skim.CMSSWVersion } )

                    if tier1Skim.Node == None:
                        tier1Skim.Node = datasetConfig.CustodialNode
                    else:
                        bindsStorageNode.append( { 'NODE' : tier1Skim.Node } )

                    if tier1Skim.Node == None:
                        raise RuntimeError, "Configured a skim without providing a skim node or a custodial site\n"

                    bindsPromptSkimConfig.append( { 'RUN' : run,
                                                    'PRIMDS' : datasetConfig.Name,
                                                    'TIER' : tier1Skim.DataTier,
                                                    'NODE' : tier1Skim.Node,
                                                    'CMSSW' : tier1Skim.CMSSWVersion,
                                                    'TWO_FILE_READ' : int(tier1Skim.TwoFileRead),
                                                    'PROC_VER' : tier1Skim.ProcessingVersion,
                                                    'SKIM_NAME' : tier1Skim.SkimName,
                                                    'GLOBAL_TAG' : tier1Skim.GlobalTag,
                                                    "CONFIG_URL" : tier1Skim.ConfigURL } )

##             elif streamConfig.ProcessingStyle == "Express":

##                 insertPhEDExConfig(dbConn, runNumber, datasetConfig.Name,
##                                    None, "T2_CH_CAF", None, False)

##                 insertPhEDExConfig(dbConn, runNumber, errorDataset,
##                                    None, "T2_CH_CAF", None, False)

        try:

            myThread.transaction.begin()

            insertDatasetDAO.execute(bindsDataset)
            insertStreamDatasetDAO.execute(bindsStreamDataset)
            insertStreamStyleDAO.execute(bindsStreamStyle)
            if len(bindsRepackConfig) > 0:
                insertRepackConfigDAO.execute(bindsRepackConfig)
            if len(bindsExpressConfig) > 0:
                insertExpressConfigDAO.execute(bindsExpressConfig)
            if len(bindsSpecialDataset) > 0:
                insertSpecialDatasetDAO.execute(bindsSpecialDataset)
            insertDatasetScenarioDAO.execute(bindsDatasetScenario)
            if len(bindsCMSSWVersion):
                insertCMSSWVersionDAO.execute(bindsCMSSWVersion)
            if len(bindsStreamOverride) > 0:
                updateStreamOverrideDAO.execute(bindsStreamOverride)
            if len(bindsErrorDataset):
                insertErrorDatasetDAO.execute(bindsErrorDataset)
            if len(bindsRecoConfig) > 0:
                insertRecoConfigDAO.execute(bindsRecoConfig)
            if len(bindsStorageNode) > 0:
                insertStorageNodeDAO.execute(bindsStorageNode)
            if len(bindsPhEDExConfig) > 0:
                insertPhEDExConfigDAO.execute(bindsPhEDExConfig)
            if len(bindsPromptSkimConfig) > 0:
                insertPromptSkimConfigDAO.execute(bindsPromptSkimConfig)

            myThread.transaction.commit()

        except Exception, e:

            myThread.transaction.rollback()
            raise

    else:

        # should we do anything for local runs ?
        pass

    return