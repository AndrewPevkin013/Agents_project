#pragma once

#include <QMainWindow>
#include <QLineEdit>
#include <QComboBox>
#include <QPlainTextEdit>
#include <QPushButton>
#include <QListWidget>
#include <QLabel>
#include <QTimer>
#include <QJsonObject>

#include "api_client.h"

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

protected:
    void dragEnterEvent(QDragEnterEvent *event) override;
    void dropEvent(QDropEvent *event) override;

private:
    ApiClient m_api;

    bool m_handlerBusy = false;
    QTimer *m_handlerTimeout = nullptr;

    QLineEdit *m_serverUrl = nullptr;
    QPlainTextEdit *m_output = nullptr;

    QPlainTextEdit *m_handlerInput = nullptr;
    QPushButton *m_handlerSendButton = nullptr;

    QListWidget *m_agentsList = nullptr;
    QLabel *m_currentAgentLabel = nullptr;
    QString m_currentAgent;

    QLineEdit *m_agentName = nullptr;
    QComboBox *m_agentType = nullptr;
    QLineEdit *m_modelName = nullptr;
    QLineEdit *m_agentTags = nullptr;
    QPlainTextEdit *m_agentPrompt = nullptr;

    QLineEdit *m_runAgentName = nullptr;
    QPlainTextEdit *m_runPrompt = nullptr;

    QLineEdit *m_docPath = nullptr;
    QPlainTextEdit *m_docText = nullptr;

    QWidget *createServerPanel();
    QWidget *createHandlerPanel();
    QWidget *createAgentsPanel();
    QWidget *createDocumentsPanel();
    QWidget *createLogsPanel();

    void updateAgentsList(const QJsonObject &json);
    void unlockHandler();
    void printJson(const QString &title, const QJsonObject &json);
    void printError(const QString &message);
};
